"""Time retained SWE-bench outcomes with/without synthetic identity declarations.

The declarations are hashes of IDs, NOT independently verified question content.
They exercise the same validation path as harness content signatures, while all
model scores and question cohorts come unchanged from the retained data file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import errorbars.leaderboard
from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "swe-bench-verified/data/outcomes.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", type=int, default=[40, 80, 120])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(SOURCE.read_text())
    questions = source["instances"]
    submissions = sorted(source["submissions"], key=lambda s: (-s["n_resolved"], s["id"]))
    signatures = [hashlib.sha256(q.encode()).hexdigest() for q in questions]
    measurements = []
    for count in args.models:
        selected = submissions[:count]
        data = EvalData(
            questions * len(selected),
            [s["id"] for s in selected for _ in questions],
            [float(bit) for s in selected for bit in f'{int(s["resolved"], 16):0{len(questions)}b}'],
        )
        for signed in (False, True):
            data.question_hash = signatures * len(selected) if signed else None
            seconds = []
            digests = set()
            for _ in range(args.repeat):
                started = time.perf_counter()
                board = build_leaderboard(data)
                seconds.append(time.perf_counter() - started)
                payload = json.dumps(board.as_dict(), sort_keys=True, allow_nan=False).encode()
                digests.add(hashlib.sha256(payload).hexdigest())
            assert len(digests) == 1
            row = {
                "models": len(selected), "questions": len(questions), "rows": len(data),
                "synthetic_identity_declarations": signed, "seconds": seconds,
                "median_seconds": statistics.median(seconds), "output_sha256": next(iter(digests)),
                "tested_pairs": len(board.pairwise),
            }
            measurements.append(row)
            print(json.dumps(row), flush=True)
    record = {
        "python": platform.python_version(), "platform": platform.platform(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "leaderboard_module_sha256": hashlib.sha256(
            Path(errorbars.leaderboard.__file__).read_bytes()
        ).hexdigest(),
        "identity_note": "Synthetic hashes of question IDs, not verified content signatures.",
        "cluster_note": "No cluster column; this measures question-level binary pair tests.",
        "measurements": measurements,
    }
    args.out.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
