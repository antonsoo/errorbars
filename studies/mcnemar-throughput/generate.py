"""Generate a labelled synthetic binary evaluation, without committing a large CSV."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SEED = 20261015
QUESTIONS = 200_000
MODELS = 8


def main() -> None:
    destination = ROOT / "cache/independent-binary.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.Generator(np.random.PCG64(SEED))
    outcomes = rng.integers(0, 2, size=(QUESTIONS, MODELS), dtype=np.int8)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["question_id", "model", "score"])
        for question, row in enumerate(outcomes):
            for model, score in enumerate(row):
                writer.writerow([f"q{question:06d}", f"model-{model}", int(score)])
    metadata = {
        "synthetic": True,
        "description": "Independent random binary outcomes; a throughput control, not model accuracy",
        "seed": SEED, "generator": "NumPy PCG64; int8 integer draws",
        "questions": QUESTIONS, "models": MODELS, "observations": QUESTIONS * MODELS,
        "bytes": destination.stat().st_size, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "successes": outcomes.sum(axis=0).tolist(),
        "pairs": [
            {"a": a, "b": b, "n01": int(np.sum((outcomes[:, a] == 0) & (outcomes[:, b] == 1))),
             "n10": int(np.sum((outcomes[:, a] == 1) & (outcomes[:, b] == 0)))}
            for a in range(MODELS) for b in range(a + 1, MODELS)
        ],
    }
    (ROOT / "results/input.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print({key: metadata[key] for key in ("questions", "models", "observations", "bytes", "sha256")})


if __name__ == "__main__":
    main()
