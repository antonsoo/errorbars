"""Check actual summaries of retained public outcomes against dense OLS CR2.

Run from a development environment (NumPy and SciPy), from the repository root:
    python studies/summary-inference/audit.py --out studies/summary-inference/results/census.json

The oracle constructs the general residual-maker matrix and cluster adjustment
matrices. It does not use errorbars' scalar intercept-only covariance or t code.
Evaluation masks are honored here; unobserved tasks are not observed failures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.stats import t

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "swe-bench-verified/data/outcomes.json"


@lru_cache(maxsize=8)
def design(groups: tuple[str, ...]) -> tuple[np.ndarray, float]:
    """General CR2 score projections and Satterthwaite df, cached by cohort."""
    x = np.ones((len(groups), 1))
    bread = np.linalg.inv(x.T @ x)
    residual = np.eye(len(groups)) - x @ bread @ x.T
    columns = []
    for group in dict.fromkeys(groups):
        rows = np.array([i for i, label in enumerate(groups) if label == group])
        values, vectors = np.linalg.eigh(residual[np.ix_(rows, rows)])
        adjustment = (vectors / np.sqrt(values)) @ vectors.T
        columns.append((residual[:, rows] @ adjustment @ x[rows] @ bread).ravel())
    projection = np.column_stack(columns)
    eigenvalues = np.linalg.eigvalsh(projection.T @ projection)
    dof = float(eigenvalues.sum() ** 2 / (eigenvalues @ eigenvalues))
    return projection, dof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(SOURCE.read_text())
    instances = data["instances"]
    width = len(instances)
    complete = (1 << width) - 1
    records, excluded = [], []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "scores.csv"
        for sub in data["submissions"]:
            # Preserve the parent study's reported-score consistency policy.
            reported = sub.get("reported")
            if reported is not None and abs(float(reported) - 100 * sub["n_resolved"] / width) > 0.5:
                excluded.append(sub["id"])
                continue
            resolved = int(sub["resolved"], 16)
            evaluated = int(sub.get("evaluated", format(complete, "x")), 16)
            assert 0 <= resolved <= complete and 0 < evaluated <= complete
            assert resolved & ~evaluated == 0
            assert resolved.bit_count() == sub["n_resolved"]
            assert evaluated.bit_count() == sub.get("n_evaluated", width)
            observed = [iid for i, iid in enumerate(instances) if evaluated & (1 << (width - i - 1))]
            scores = [float(bool(resolved & (1 << (width - i - 1)))) for i in range(width)
                      if evaluated & (1 << (width - i - 1))]
            groups = tuple(iid.rsplit("-", 1)[0].replace("__", "/") for iid in observed)
            with source.open("w") as stream:
                writer = csv.writer(stream)
                writer.writerow(["question_id", "model", "score", "cluster_id"])
                writer.writerows(zip(observed, [sub["id"]] * len(observed), scores, groups, strict=True))
            run = subprocess.run(
                [sys.executable, "-m", "errorbars.cli", "summarize", str(source), "--json"],
                capture_output=True, text=True, check=True,
            )
            assert not run.stderr, run.stderr
            summary = json.loads(run.stdout)
            projection, dof = design(groups)
            cluster_scores = np.asarray(scores) @ projection
            se = float(np.sqrt(cluster_scores @ cluster_scores))
            mean = float(np.mean(scores))
            half_width = float(t.ppf(0.975, dof)) * se
            expected = np.array([mean, se, mean - half_width, mean + half_width, dof])
            actual = np.array([summary[k] for k in ("mean", "se", "ci_low", "ci_high", "dof_clustered")])
            assert summary["method"] == "clustered_cr2" and summary["interval_status"] == "available"
            assert summary["n"] == len(observed) and summary["n_clusters"] == len(set(groups))
            assert np.allclose(actual, expected, rtol=1e-11, atol=1e-12), sub["id"]
            diagnostic = summary["unclustered"]
            records.append({
                "model": sub["id"], "n": len(observed), "n_clusters": len(set(groups)),
                "mean": mean, "se": summary["se"], "ci": [summary["ci_low"], summary["ci_high"]],
                "dof": dof, "independent_ci": [diagnostic["ci_low"], diagnostic["ci_high"]],
                "independent_method": diagnostic["method"],
                "max_oracle_absolute_error": float(np.max(np.abs(actual - expected))),
                "reported_benchmark_percent": reported,
            })
    result = {
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "python": sys.version.split()[0], "numpy": np.__version__,
        "confidence": 0.95, "submissions": len(records), "excluded": excluded,
        "complete_cohorts": sum(r["n"] == width for r in records),
        "partial_cohorts": sum(r["n"] != width for r in records),
        "clustered_intervals_wider": sum(r["ci"][1] - r["ci"][0] >
                                         r["independent_ci"][1] - r["independent_ci"][0] for r in records),
        "max_oracle_absolute_error": max(r["max_oracle_absolute_error"] for r in records),
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}))


if __name__ == "__main__":
    main()
