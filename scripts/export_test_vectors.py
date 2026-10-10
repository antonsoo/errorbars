#!/usr/bin/env python3
"""Export power-formula test vectors from the Python implementation.

The web calculator re-implements the same formulas in TypeScript for a
zero-latency UI; its vitest suite checks against these vectors so the two
implementations can never silently drift apart. Run this after changing
anything in ``src/errorbars/power.py``.
"""

from __future__ import annotations

import itertools
import json
import random
from pathlib import Path

from scipy.special import ndtri

from errorbars.power import minimum_detectable_effect, questions_needed

OUT_PATH = Path(__file__).parent.parent / "web" / "test-vectors.json"


def main() -> None:
    vectors = []

    baselines = [0.001, 0.3, 0.5, 0.7, 0.9, 0.999]
    deltas = [0.0001, 0.001, 0.01, 0.03, 0.05, 0.1, 0.5]
    alphas = [0.001, 0.05, 0.1, 0.2]
    powers = [0.5, 0.8, 0.9, 0.999]
    rhos = [-0.95, 0.0, 0.3, 0.6, 0.95]
    samples = [1, 2, 4]
    deffs = [1.0, 1.5, 3.0, 1000.0]
    rng = random.Random(20261003)
    repeat_rng = random.Random(20261009)

    # Sample the entire Cartesian product. Taking its first 400 entries covered only
    # baseline=0.3; the inverse vectors likewise covered only n=50.
    forward_cases = [
        case
        for case in itertools.product(baselines, deltas, alphas, powers, rhos, samples, deffs)
        if case[0] + case[1] <= 1
    ]
    for baseline, delta, alpha, power, rho, k, deff in rng.sample(forward_cases, 400):
        repeat_correlation = None if k == 1 else repeat_rng.choice([0.0, 1 / 3, 0.8, 1.0])
        result = questions_needed(
            delta=delta,
            baseline_accuracy=baseline,
            alpha=alpha,
            power=power,
            rho=rho,
            samples_per_question=k,
            repeat_correlation=repeat_correlation,
            cluster_design_effect=deff,
        )
        vectors.append(
            {
                "inputs": {
                    "baseline": baseline,
                    "delta": delta,
                    "alpha": alpha,
                    "power": power,
                    "rho": rho,
                    "samplesPerQuestion": k,
                    "repeatCorrelation": repeat_correlation,
                    "clusterDeff": deff,
                },
                "nQuestions": result.n_questions,
                "perQuestionVariance": result.per_question_variance,
            }
        )

    mde_vectors = []
    ns = [2, 50, 100, 300, 1000, 5000, 1_000_000_000]
    for n, baseline, alpha, power, rho, k, deff in rng.sample(
        list(itertools.product(ns, baselines, alphas, powers, rhos, samples, deffs)), 200
    ):
        repeat_correlation = None if k == 1 else repeat_rng.choice([0.0, 1 / 3, 0.8, 1.0])
        mde = minimum_detectable_effect(
            n_questions=n,
            baseline_accuracy=baseline,
            alpha=alpha,
            power=power,
            rho=rho,
            samples_per_question=k,
            repeat_correlation=repeat_correlation,
            cluster_design_effect=deff,
        )
        mde_vectors.append(
            {
                "inputs": {
                    "n": n,
                    "baseline": baseline,
                    "alpha": alpha,
                    "power": power,
                    "rho": rho,
                    "samplesPerQuestion": k,
                    "repeatCorrelation": repeat_correlation,
                    "clusterDeff": deff,
                },
                "mde": mde,
            }
        )

    probabilities = [
        5e-324,
        1e-300,
        1e-30,
        1e-12,
        1e-8,
        0.0005,
        0.001,
        0.01,
        0.02425,
        0.025,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        0.8,
        0.9,
        0.925,
        0.975,
        0.99,
        0.999,
        1 - 1e-8,
        1 - 1e-12,
        1 - 2**-53,
    ]
    quantiles = [{"p": p, "z": float(ndtri(p))} for p in probabilities]
    payload = {
        "questionsNeeded": vectors,
        "minimumDetectableEffect": mde_vectors,
        "normalQuantiles": quantiles,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote {len(vectors)} questions-needed vectors and {len(mde_vectors)} MDE vectors to {OUT_PATH}")


if __name__ == "__main__":
    main()
