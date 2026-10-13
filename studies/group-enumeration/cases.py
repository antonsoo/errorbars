"""Constructed binary scores; no measured model performance or private inputs."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def write_case(path: Path, pairs: int) -> None:
    if not 1 <= pairs <= 25:
        raise ValueError("pairs must be between 1 and 25")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "question_id", "score"])
        for pair in range(1, pairs + 1):
            corrected = 0
            for question in range(1024):
                score = (question & pair).bit_count() % 2
                edited = score
                if score == 0 and corrected < 16:
                    edited = 1
                    corrected += 1
                writer.writerow([f"pair-{pair:02}-base", f"q-{question:04}", score])
                writer.writerow([f"pair-{pair:02}-edit", f"q-{question:04}", edited])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pairs", type=int, default=25)
    args = parser.parse_args()
    write_case(args.output, args.pairs)
