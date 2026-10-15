"""Replay native changed-grader and common-grader controls through actual CLI paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from errorbars.inputs import load_inputs
from errorbars.leaderboard import build_leaderboard
from errorbars.review import review_comparison

HERE = Path(__file__).resolve().parent


def samples(label: str) -> list[dict]:
    path = next((HERE / "captures" / label).rglob("samples_*.jsonl"))
    return [json.loads(line) for line in path.read_text().splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    records = []
    a = samples("strict")
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
        work = Path(temporary).resolve()
        for label in ("folded", "strict-repeat", "improved-strict", "prompt-variant"):
            b = samples(label)
            assert [(r["doc"], r["target"]) for r in a] == [(r["doc"], r["target"]) for r in b]
            specs = [f"A={HERE / 'captures/strict'}", f"B={HERE / 'captures' / label}"]
            data = load_inputs(specs).data
            review = review_comparison(data, "A", "B")
            inference = review.inference
            discordant = [sum(x["exact_match"] < y["exact_match"] for x, y in zip(a, b, strict=True)),
                          sum(x["exact_match"] > y["exact_match"] for x, y in zip(a, b, strict=True))]
            total = sum(discordant)
            exact = min(1., 2 * sum(math.comb(total, i) for i in range(min(discordant) + 1)) / 2**total)
            record = {
                "other_run": label, "same_questions_targets": True,
                "same_answers": [r["resps"] for r in a] == [r["resps"] for r in b],
                "same_prompt_arguments": [r["arguments"] for r in a] == [r["arguments"] for r in b],
                "cohort": review.cohort, "inference": inference.as_dict() if inference else None,
                "raw_score_exact_p": exact, "unavailable_reason": review.unavailable_reason,
                "config_fingerprints": [data.scoring[0].config_hash, data.scoring[len(a)].config_hash],
            }
            try:
                board = build_leaderboard(data)
                record["leaderboard"] = {"status": "accepted", "entries": len(board.entries)}
            except ValueError as exc:
                record["leaderboard"] = {"status": "refused", "reason": str(exc)}
            report = work / f"{label}.html"
            for command in ("compare", "leaderboard"):
                arguments = [sys.executable, "-m", "errorbars.cli", command, *specs, "--json"]
                if command == "compare":
                    arguments.extend(["--html", str(report)])
                result = subprocess.run(arguments, capture_output=True, text=True, check=False)
                assert "Traceback" not in result.stderr, result.stderr
                record[command + "_cli"] = {
                    "exit": result.returncode, "stdout": bool(result.stdout),
                    "scoring_conflict": "conflicting scoring rules" in result.stderr,
                }
                if result.stdout:
                    payload = json.loads(result.stdout)
                    if command == "compare":
                        record[command + "_cli"]["inference"] = payload["inference"]
            record["html_created"] = report.is_file()
            assert report.is_file()
            if args.artifacts:
                args.artifacts.mkdir(parents=True, exist_ok=True)
                (args.artifacts / report.name).write_bytes(report.read_bytes())
            records.append(record)
    files = sorted((HERE / "captures").rglob("*.json")) + sorted((HERE / "captures").rglob("*.jsonl"))
    result = {
        "python": platform.python_version(), "cases": records,
        "inputs": [{"path": str(path.relative_to(HERE)), "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files],
        "changed_grader_inference_withheld": records[0]["inference"] is None,
        "common_grader_controls_usable": all(record["inference"] is not None for record in records[1:]),
    }
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"changed_grader_inference_withheld": result["changed_grader_inference_withheld"],
                      "common_grader_controls_usable": result["common_grader_controls_usable"],
                      "cli_workflows": len(records) * 2}))


if __name__ == "__main__":
    main()
