"""Replay the actual summary CLI from source or a bare installed artifact.

Only the installed package's required NumPy dependency is needed. Retained oracle
values were separately calculated by audit.py with general OLS CR2 and SciPy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import errorbars._mean

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "insufficient-cohorts/scores.csv"
MODEL = "20251205_sonar-foundation-agent_claude-opus-4-5"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    census = json.loads((HERE / "results/census.json").read_text())
    oracle = next(row for row in census["records"] if row["model"] == MODEL)
    records = {}

    def invoke(source: Path, *options: str) -> dict:
        result = subprocess.run(
            [sys.executable, "-m", "errorbars.cli", "summarize", str(source), "--json", *options],
            capture_output=True, text=True, check=True,
        )
        assert not result.stderr, result.stderr
        return json.loads(result.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        for method in ("auto", "clt", "wilson", "bootstrap"):
            summary = invoke(SOURCE, "--model", MODEL, "--ci", method)
            assert summary["method"] == "clustered_cr2" and summary["interval_status"] == "available"
            assert summary["mean"] == oracle["mean"] and summary["n_clusters"] == oracle["n_clusters"]
            assert np.allclose([summary["se"], summary["ci_low"], summary["ci_high"]],
                               [oracle["se"], *oracle["ci"]], rtol=1e-11, atol=1e-12)
            assert summary["unclustered"]["method"] == ("clt" if method == "auto" else method)
            independent = invoke(SOURCE, "--model", MODEL, "--ci", method, "--cluster-col", "none")
            assert independent["method"] == summary["unclustered"]["method"]
            for key in ("mean", "se", "ci_low", "ci_high"):
                assert independent[key] == summary["unclustered"][key]
            records[method] = summary
        partial = invoke(SOURCE, "--model", "django-only")
        assert partial["n"] == 231 and partial["mean"] == 191 / 231
        assert partial["n_clusters"] == 1 and partial["interval_status"] == "fewer_than_two_clusters"
        assert partial["se"] is partial["ci_low"] is partial["ci_high"] is None
        assert partial["unclustered"]["ci_low"] is not None
        records["one-cluster"] = partial
        for name, rows in {
            "one-continuous": "q,m,0.3,0\n",
            "one-repeated": "q,m,0,0\nq,m,1,1\n",
            "unequal-repetition": "".join(f"q1,m,0,{i}\n" for i in range(12))
            + "q2,m,1,0\nq3,m,1,0\n",
            "one-binary": "q,m,1,0\n",
        }.items():
            source = Path(tmp) / f"{name}.csv"
            source.write_text("question_id,model,score,sample\n" + rows)
            result = invoke(source)
            if name.startswith("one-") and name != "one-binary":
                assert result["interval_status"] == "fewer_than_two_questions"
                assert result["se"] is result["ci_low"] is result["ci_high"] is None
            elif name == "one-binary":
                assert result["method"] == "wilson" and result["ci_high"] == 1.0
            else:
                assert result["mean"] == 2 / 3 and result["n"] == 3 and result["n_observations"] == 14
            records[name] = result
    output = {
        "python": sys.version.split()[0], "numpy": np.__version__,
        "policy_module_sha256": hashlib.sha256(Path(errorbars._mean.__file__).read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "cases": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"cases": len(records), "python": output["python"], "numpy": output["numpy"]}))


if __name__ == "__main__":
    main()
