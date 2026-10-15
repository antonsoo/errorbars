"""Time the real CLI and public comparison API under the invoking Python installation."""

import argparse
import hashlib
import json
import platform
import resource
import statistics
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from errorbars.compare import mcnemar_exact

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("--kernel-only", action="store_true")
    parser.add_argument("--cli-only", action="store_true")
    parser.add_argument("--input", type=Path, default=ROOT / "cache/independent-binary.csv")
    args = parser.parse_args()
    measurements = []
    counts = [] if args.cli_only else [(1_000, 450), (10_000, 4_900), (100_000, 49_500), (200_000, 99_500)]
    for total, k in counts:
        a = np.r_[np.zeros(k), np.ones(total - k)]
        b = 1 - a
        times = []
        for _ in range(3):
            start = perf_counter()
            result = mcnemar_exact(a, b)
            times.append(perf_counter() - start)
        measurements.append({"discordant": total, "n01": k, "n10": total - k,
                             "seconds": times, "median_seconds": statistics.median(times),
                             "p_value": result.p_value})
    receipt = {"python": platform.python_version(), "synthetic": True, "kernel": measurements}
    if not args.kernel_only:
        source = args.input
        output = ROOT / f"results/{args.label}-leaderboard.json"
        start = perf_counter()
        usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        with output.open("w", encoding="utf-8") as stream:
            subprocess.run([sys.executable, "-m", "errorbars.cli", "leaderboard", str(source), "--json"],
                           stdout=stream, check=True, timeout=180)
        elapsed = perf_counter() - start
        usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        board = json.loads(output.read_text())
        assert len(board["entries"]) == 8 and len(board["pairwise"]) == 28
        assert all(pair["test"] == "mcnemar_exact" for pair in board["pairwise"])
        receipt["cli"] = {"seconds": elapsed, "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                          "user_cpu_seconds": usage_after.ru_utime - usage_before.ru_utime,
                          "system_cpu_seconds": usage_after.ru_stime - usage_before.ru_stime,
                          "peak_rss_kib_linux": usage_after.ru_maxrss,
                          "models": len(board["entries"]), "pairs": len(board["pairwise"]),
                          "command": "errorbars leaderboard independent-binary.csv --json",
                          "output": output.name}
    (ROOT / f"results/{args.label}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
