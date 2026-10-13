"""Replay the retained usable SWE-bench submissions, with both inference scopes."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import errorbars.leaderboard
from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
source = args.root / "studies/swe-bench-verified/data/outcomes.json"
raw = source.read_bytes()
data = json.loads(raw)
questions = data["instances"]
submissions = [s for s in data["submissions"] if s.get("reported") is None
               or abs(float(s["reported"]) - 100 * s["n_resolved"] / len(questions)) <= 0.5]
table = EvalData(
    questions * len(submissions),
    [s["id"] for s in submissions for _ in questions],
    [float(bit) for s in submissions for bit in f'{int(s["resolved"], 16):0{len(questions)}b}'],
)
args.out.mkdir(parents=True, exist_ok=True)
results = []
for clustered in [False, True]:
    name = "clustered" if clustered else "question"
    table.cluster_id = ([q.rsplit("-", 1)[0] for q in questions] * len(submissions)
                        if clustered else None)
    started = time.perf_counter()
    board = build_leaderboard(table)
    seconds = time.perf_counter() - started
    report = board.as_dict()
    # The new status describes summary availability; compare all prior fields.
    status = report.pop("group_status", "complete")
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    (args.out / (name + ".json")).write_bytes(encoded)
    result = {"scope": name, "models": len(board.entries), "pairs": len(board.pairwise),
              "groups": len(board.groups) if board.groups is not None else None,
              "groupStatus": status, "seconds": seconds,
              "completeReportSha256WithoutGroupStatus": hashlib.sha256(encoded).hexdigest()}
    results.append(result)
    print(json.dumps(result), flush=True)
(args.out / "receipt.json").write_text(json.dumps({
    "python": platform.python_version(), "sourceFileSha256": hashlib.sha256(raw).hexdigest(),
    "implementationSha256": hashlib.sha256(Path(errorbars.leaderboard.__file__).read_bytes()).hexdigest(),
    "questions": len(questions), "usableSubmissions": len(submissions),
    "excludedSubmissions": len(data["submissions"]) - len(submissions), "results": results,
    "note": ("Retained public outcomes; not a new crawl or accuracy study. All prior report fields "
             "are hashed, including complete groups, inference, warnings and rank comparisons."),
}, indent=2) + "\n")
