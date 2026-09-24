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
from pathlib import Path

from errorbars.power import minimum_detectable_effect, questions_needed

OUT_PATH = Path(__file__).parent.parent / "web" / "test-vectors.json"


def main() -> None:
    vectors = []

    baselines = [0.3, 0.5, 0.7, 0.9]
    deltas = [0.01, 0.03, 0.05, 0.1]
    alphas = [0.05, 0.1]
    powers = [0.8, 0.9]
    rhos = [0.0, 0.3, 0.6]
    samples = [1, 2, 4]
    deffs = [1.0, 1.5, 3.0]

    for baseline, delta, alpha, power, rho, k, deff in itertools.islice(
        itertools.product(baselines, deltas, alphas, powers, rhos, samples, deffs), 0, 400
    ):
        result = questions_needed(
            delta=delta,
            baseline_accuracy=baseline,
            alpha=alpha,
            power=power,
            rho=rho,
            samples_per_question=k,
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
                    "clusterDeff": deff,
                },
                "nQuestions": result.n_questions,
                "perQuestionVariance": result.per_question_variance,
            }
        )

    mde_vectors = []
    ns = [50, 100, 300, 1000, 5000]
    for n, baseline, alpha, power, rho, k, deff in itertools.islice(
        itertools.product(ns, baselines, alphas, powers, rhos, samples, deffs), 0, 200
    ):
        mde = minimum_detectable_effect(
            n_questions=n,
            baseline_accuracy=baseline,
            alpha=alpha,
            power=power,
            rho=rho,
            samples_per_question=k,
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
                    "clusterDeff": deff,
                },
                "mde": mde,
            }
        )

    payload = {"questionsNeeded": vectors, "minimumDetectableEffect": mde_vectors}
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote {len(vectors)} questions-needed vectors and {len(mde_vectors)} MDE vectors to {OUT_PATH}")


if __name__ == "__main__":
    main()
