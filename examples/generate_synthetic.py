#!/usr/bin/env python3
"""Generate a SYNTHETIC clustered reading-comprehension benchmark.

Simulates 4 models answering multiple-choice questions grouped into
passages (5 questions/passage). Correctness depends on a shared
passage-difficulty effect and question-difficulty effect (so questions in
the same passage are correlated -- the reason clustered SEs matter here)
plus a per-model ability level and per-(model, question) idiosyncratic
noise. All numbers in this file are simulated; they do not describe any
real model. Run with: `python examples/generate_synthetic.py`.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

SEED = 20260924
N_PASSAGES = 40
QUESTIONS_PER_PASSAGE = 5
MODELS = {
    # name -> (ability logit, idiosyncratic-noise sd)
    "baseline-7b": (-0.35, 0.55),
    "tuned-7b": (0.05, 0.55),
    "baseline-70b": (0.55, 0.45),
    "tuned-70b": (0.68, 0.45),  # true edge over baseline-70b is small and noisy on purpose
}
SIGMA_PASSAGE = 0.9
SIGMA_QUESTION = 0.5


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def main() -> None:
    rng = np.random.default_rng(SEED)
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)

    rows: list[dict[str, object]] = []
    for passage_idx in range(N_PASSAGES):
        passage_id = f"passage-{passage_idx:03d}"
        passage_effect = rng.normal(0, SIGMA_PASSAGE)
        for q_idx in range(QUESTIONS_PER_PASSAGE):
            question_id = f"{passage_id}-q{q_idx}"
            question_effect = rng.normal(0, SIGMA_QUESTION)
            for model, (ability, noise_sd) in MODELS.items():
                logit = ability + passage_effect + question_effect + rng.normal(0, noise_sd)
                p_correct = sigmoid(logit)
                score = int(rng.uniform() < p_correct)
                rows.append(
                    {
                        "question_id": question_id,
                        "cluster_id": passage_id,
                        "model": model,
                        "score": score,
                    }
                )

    out_path = out_dir / "reading_comprehension.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question_id", "cluster_id", "model", "score"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {out_path}")

    # A second, smaller dataset with repeated samples per question (decoding
    # noise), for the within/between-question variance decomposition demo.
    rows2: list[dict[str, object]] = []
    n_questions = 60
    samples_per_question = 4
    ability = 0.2
    for q_idx in range(n_questions):
        question_id = f"q-{q_idx:03d}"
        question_effect = rng.normal(0, 0.7)  # item difficulty (between-question)
        for s in range(samples_per_question):
            logit = ability + question_effect + rng.normal(0, 0.6)  # decoding noise (within-question)
            score = int(rng.uniform() < sigmoid(logit))
            rows2.append(
                {
                    "question_id": question_id,
                    "model": "tuned-7b",
                    "sample": s,
                    "score": score,
                }
            )
    out_path2 = out_dir / "repeated_sampling.csv"
    with open(out_path2, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question_id", "model", "sample", "score"])
        writer.writeheader()
        writer.writerows(rows2)
    print(f"wrote {len(rows2)} rows to {out_path2}")


if __name__ == "__main__":
    main()
