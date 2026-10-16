"""Measure full repeated-score CSV loading and leaderboard analysis, not a kernel."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

from errorbars import io

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--work", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
args.work.mkdir(parents=True, exist_ok=True)
source = args.work / "repeated.csv"
with source.open("w", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["question_id", "model", "score", "sample"])
    for model, repeat in (("once", 1), ("triple", 3), ("ten", 10)):
        for question in range(5000):
            for sample, score in enumerate([0.1, 0.2, 0.3] * repeat):
                writer.writerow([question, model, repr(score), sample])
samples = []
for _ in range(3):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    process = subprocess.run(
        [sys.executable, "-m", "errorbars.cli", "leaderboard", str(source.resolve()), "--json"],
        text=True,
        capture_output=True,
        check=True,
    )
    elapsed = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = json.loads(process.stdout)
    samples.append(
        {
            "wall_seconds": elapsed,
            "child_cpu_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
            "groups": result["groups"],
            "p_holm": [pair["p_holm"] for pair in result["pairwise"]],
        }
    )
receipt = {
    "rows": 210000,
    "questions": 5000,
    "models": 3,
    "repeats": 3,
    "python": sys.version.split()[0],
    "io_sha256": hashlib.sha256(Path(io.__file__).read_bytes()).hexdigest(),
    "input_bytes": source.stat().st_size,
    "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "scope": "Synthetic identical grade distributions; shared host; no general speed claim",
    "samples": samples,
}
args.out.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(samples))
