"""Audit repeated-answer planning using retained outcomes and independent power oracles.

Run from the repository: uv run python studies/repeated-planning/analyze.py
No network or raw model answers are needed. The study requires dev dependencies.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import nct, norm, t

from errorbars.power import per_question_variance, questions_needed

ROOT = Path(__file__).resolve().parent
COUNTS = [1, 2, 4, 10, 100]


def simulate(n: int, k: int, between: float, within: float, trials: int, seed: int) -> dict:
    """Normal random effects: independently sample question and generation noise.

    The average of k normal generation errors is normal with variance W/k.
    Sample the two components separately; do not use errorbars' variance helper.
    Test the per-question paired differences with their estimated SD (Student t).
    """
    rng = np.random.default_rng(seed)
    critical = t.isf(0.025, n - 1)
    rejections = 0
    for start in range(0, trials, 256):
        shape = (min(256, trials - start), n)
        difference = rng.normal(0.05, math.sqrt(2 * between), size=shape)
        difference += rng.normal(0, math.sqrt(2 * within / k), size=shape)
        statistic = difference.mean(axis=1) / (difference.std(axis=1, ddof=1) / math.sqrt(n))
        rejections += int((np.abs(statistic) > critical).sum())
    empirical = rejections / trials
    noncentrality = 0.05 * math.sqrt(n / (2 * between + 2 * within / k))
    exact = float(nct.sf(critical, n - 1, noncentrality) + nct.cdf(-critical, n - 1, noncentrality))
    mc_se = math.sqrt(empirical * (1 - empirical) / trials)
    assert abs(empirical - exact) < 5 * mc_se
    return {
        "n_questions": n,
        "model_answers": 2 * n * k,
        "empirical_power": empirical,
        "monte_carlo_se": mc_se,
        "noncentral_t_power": exact,
        "rejections": rejections,
    }


def simulated_plans(trials: int) -> list[dict]:
    rows = []
    z_sum = norm.isf(0.025) + norm.ppf(0.8)
    for index, (k, r) in enumerate([(10, 0.0), (4, 1 / 3), (100, 0.8), (100, 1.0)]):
        # Reproduce the old V/k formula without importing historical code.
        old_n = max(2, math.ceil(z_sum**2 * (2 * 0.25 / k) / 0.05**2))
        new = questions_needed(0.05, variance=0.25, samples_per_question=k, repeat_correlation=r)
        between, within = 0.25 * r, 0.25 * (1 - r)
        rows.append(
            {
                "samples_per_question": k,
                "repeat_correlation": r,
                "target_power": 0.8,
                "between_variance": between,
                "within_variance": within,
                "old": simulate(old_n, k, between, within, trials, 4200 + index),
                "repaired": simulate(new.n_questions, k, between, within, trials, 5200 + index),
            }
        )
    return rows


def public_outcomes() -> dict:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    packed = (ROOT / "outcomes.json.gz").read_bytes()
    assert hashlib.sha256(packed).hexdigest() == manifest["outcomes_sha256"]
    raw = gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest() == manifest["outcomes_json_sha256"]
    data = json.loads(raw)
    assert data["schema_version"] == 1 and len(data["datasets"]) == 2
    datasets, heldout, identities = [], [], []
    for dataset in data["datasets"]:
        questions = sorted(dataset["questions"], key=lambda q: int(q["question_id"]))
        identities.append([(q["question_id"], q["question_target_sha256"]) for q in questions])
        scores = np.array([[int(bit) for bit in q["correct"]] for q in questions], dtype=float)
        assert scores.shape == (127, 10_000) and np.isin(scores, [0, 1]).all()
        pilot, check = scores[:, :5000], scores[:, 5000:]
        heldout.append(check)
        # Balanced one-way moments written directly from the binary observations.
        # The check half contributes to none of these fitted components.
        within = float(np.var(pilot, axis=1, ddof=1).mean())
        between_untruncated = float(np.var(pilot.mean(axis=1), ddof=1)) - within / pilot.shape[1]
        between = max(0.0, between_untruncated)
        total = between + within
        correlation = between / total
        baseline = float(pilot.mean())
        rows = []
        for k in COUNTS:
            # Many disjoint k-answer blocks from the other 5000 draws. Every
            # block uses all 127 questions, each with weight 1/127.
            block_means = check.reshape(127, -1, k).mean(axis=2)
            observed = float(block_means.var(axis=0, ddof=1).mean())
            independent = baseline * (1 - baseline) / k
            predicted = per_question_variance(
                variance=total, samples_per_question=k, repeat_correlation=correlation
            )
            assert math.isclose(predicted, between + within / k, rel_tol=1e-12)
            rows.append(
                {
                    "samples_per_question": k,
                    "disjoint_blocks": check.shape[1] // k,
                    "observed_question_variance": observed,
                    "old_independent_prediction": independent,
                    "pilot_component_prediction": predicted,
                    "observed_over_old": observed / independent,
                    "relative_prediction_error": predicted / observed - 1,
                }
            )
        datasets.append(
            {
                "source": dataset["source"],
                "n_questions": 127,
                "n_outcomes": int(scores.size),
                "pilot_draws_per_question": 5000,
                "check_draws_per_question": 5000,
                "pilot_accuracy": baseline,
                "pilot_between_variance": between,
                "pilot_within_variance": within,
                "pilot_repeat_correlation": correlation,
                "variance_by_repeat_count": rows,
            }
        )
    assert identities[0] == identities[1], "model records do not describe the same questions/targets"
    correlations = []
    for k in COUNTS:
        a, b = [matrix.reshape(127, -1, k).mean(axis=2) for matrix in heldout]
        a, b = a - a.mean(axis=0), b - b.mean(axis=0)
        correlations.append(
            {
                "samples_per_question": k,
                "mean_paired_correlation": float(
                    ((a * b).sum(axis=0) / np.sqrt((a * a).sum(axis=0) * (b * b).sum(axis=0))).mean()
                ),
            }
        )
    return {
        "outcomes_sha256": manifest["outcomes_sha256"],
        "datasets": datasets,
        "paired_correlations_on_check_draws": correlations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=20_000)
    parser.add_argument("--out", type=Path, default=ROOT / "results.json")
    args = parser.parse_args()
    if args.trials < 1000:
        parser.error("use at least 1000 trials")
    report = {
        "schema_version": 1,
        "simulation": {
            "trials_per_plan": args.trials,
            "delta": 0.05,
            "variance": 0.25,
            "alpha": 0.05,
            "power": 0.8,
            "rho": 0,
            "cluster_design_effect": 1,
            "scenarios": simulated_plans(args.trials),
        },
        "public_outcomes": public_outcomes(),
    }
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    for row in report["simulation"]["scenarios"]:
        print(
            f"k={row['samples_per_question']:3} r={row['repeat_correlation']:.3f}: "
            f"old n={row['old']['n_questions']:4}, power={row['old']['empirical_power']:.3f}; "
            f"repaired n={row['repaired']['n_questions']:4}, power={row['repaired']['empirical_power']:.3f}"
        )
    for dataset in report["public_outcomes"]["datasets"]:
        last = dataset["variance_by_repeat_count"][-1]
        print(
            f"{dataset['source']}: repeat correlation={dataset['pilot_repeat_correlation']:.4f}; "
            f"at k=100, observed/old variance={last['observed_over_old']:.2f}; "
            f"pilot prediction error={last['relative_prediction_error']:.2%}"
        )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
