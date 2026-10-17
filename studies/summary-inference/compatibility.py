"""Compare complete actual leaderboard JSON before/after the shared mean policy.

Archive the baseline revision's src directory, then pass that directory with
--baseline-src. The current interpreter must have the corrected package installed.
Only hashes and counts are retained; neither multi-megabyte board is committed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    census = json.loads((HERE / "results/census.json").read_text())
    source = HERE.parent / "swe-bench-verified/data/outcomes.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == census["source_sha256"]
    data = json.loads(source.read_text())
    wanted = {row["model"] for row in census["records"]}
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["question_id", "model", "score", "cluster_id"])
    width = len(data["instances"])
    for sub in data["submissions"]:
        if sub["id"] not in wanted:
            continue
        resolved = int(sub["resolved"], 16)
        evaluated = int(sub.get("evaluated", format((1 << width) - 1, "x")), 16)
        for i, iid in enumerate(data["instances"]):
            bit = 1 << (width - i - 1)
            if evaluated & bit:
                writer.writerow([iid, sub["id"], int(bool(resolved & bit)),
                                 iid.rsplit("-", 1)[0].replace("__", "/")])
    raw = stream.getvalue().encode()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scores.csv"
        path.write_bytes(raw)
        for baseline in (True, False):
            env = dict(os.environ)
            if baseline:
                env["PYTHONPATH"] = str(args.baseline_src.resolve())
            else:
                env.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, "-m", "errorbars.cli", "leaderboard", str(path), "--json"],
                cwd=tmp, env=env, capture_output=True, text=True, check=True,
            )
            assert not result.stderr, result.stderr
            results.append(json.loads(result.stdout))
    assert results[0] == results[1], "shared mean selection changed existing leaderboard JSON"
    board = results[1]
    canonical = json.dumps(board, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    output = {
        "baseline_revision": json.loads((HERE / "results/before.json").read_text())["revision"],
        "baseline_cli_sha256": hashlib.sha256(
            (args.baseline_src / "errorbars/cli.py").read_bytes()
        ).hexdigest(),
        "source_sha256": census["source_sha256"],
        "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "csv_observations": sum(e["n_observations"] for e in board["entries"]),
        "models": len(board["entries"]), "pairwise": len(board["pairwise"]),
        "untested_pairs": len(board["untested_pairs"]), "groups": len(board["groups"]),
        "complete_json_unchanged": True, "canonical_json_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
