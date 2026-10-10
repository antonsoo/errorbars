"""Run the actual CLI against native harness captures and labelled selection controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "studies/lm-eval-evidence"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--src", type=Path, help="Source tree to import; omit for installed wheel")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    work = STUDY / "cache/replay"
    work.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / "tests/fixtures"
    arc = next(fixtures.glob("samples_arc_easy_*.jsonl"))
    tiny = next((fixtures / "lm_eval_output/sshleifer__tiny-gpt2").glob("samples_*.jsonl"))
    random_result = next(
        (fixtures / "lm_eval_output/hf-internal-testing__tiny-random-gpt2").glob("results_*.json")
    )
    exact = next((STUDY / "captures/exact-first").rglob("samples_*.jsonl"))
    folded = next((STUDY / "captures/casefold-first").rglob("samples_*.jsonl"))
    records_a = [json.loads(line) for line in exact.read_text().splitlines()]
    records_b = [json.loads(line) for line in folded.read_text().splitlines()]
    # Independent check of the only intended change: insertion order in metrics.
    assert len(records_a) == len(records_b) == 24
    for a, b in zip(records_a, records_b, strict=True):
        assert a["metrics"] == ["exact", "casefold"]
        assert b["metrics"] == ["casefold", "exact"]
        assert {k: v for k, v in a.items() if k != "metrics"} == {
            k: v for k, v in b.items() if k != "metrics"
        }
        assert a["filtered_resps"] == ["lol"] and a["target"] == "LOL"
        assert a["exact"] == 0 and a["casefold"] == 1
    foreign = work / "foreign"
    foreign.mkdir(exist_ok=True)
    shutil.copyfile(tiny, foreign / tiny.name)
    shutil.copyfile(random_result, foreign / random_result.name)
    renamed = foreign / "renamed.jsonl"
    shutil.copyfile(tiny, renamed)
    narrowed = []
    for label, records, chosen in [("a", records_a, "exact"), ("b", records_b, "casefold")]:
        folder = work / label
        folder.mkdir(exist_ok=True)
        path = folder / exact.name
        path.write_text("".join(json.dumps({**r, "metrics": [chosen]}) + "\n" for r in records))
        narrowed.append(path)
    mixed = work / exact.name
    mixed.write_text(
        "".join(
            json.dumps({**r, "metrics": ["exact" if i < 12 else "casefold"]}) + "\n"
            for i, r in enumerate(records_a)
        )
    )
    rel = lambda path: str(path.relative_to(ROOT))  # noqa: E731
    pair = [f"A={rel(exact)}", f"B={rel(folded)}"]
    cases = [
        ("native-order-comparison", ["compare", *pair, "--json"], "reject", "multiple metrics"),
        ("native-order-leaderboard", ["leaderboard", *pair, "--json"], "reject", "multiple metrics"),
        ("native-explicit-exact", ["compare", *pair, "--metric", "exact", "--json"], "equal", None),
        ("native-explicit-casefold", ["compare", *pair, "--metric", "casefold", "--json"], "equal", None),
        ("native-arc-ambiguous", ["summarize", f"arc={rel(arc)}", "--json"], "reject", "multiple metrics"),
        (
            "metadata-as-score",
            ["summarize", f"arc={rel(arc)}", "--metric", "doc_id", "--json"],
            "reject",
            "not declared",
        ),
        ("matching-model-metadata", ["summarize", rel(tiny), "--json"], "tiny", None),
        (
            "foreign-model-metadata",
            ["summarize", rel(foreign / tiny.name), "--json"],
            "reject",
            "matching-timestamp",
        ),
        ("renamed-model-metadata", ["summarize", rel(renamed), "--json"], "reject", "matching-timestamp"),
        ("explicit-model-name", ["summarize", f"explicit={rel(renamed)}", "--json"], "named", None),
        (
            "constructed-metric-switch",
            ["summarize", f"control={rel(mixed)}", "--json"],
            "reject",
            "not declared",
        ),
        (
            "constructed-cross-log-mismatch",
            ["compare", f"A={rel(narrowed[0])}", f"B={rel(narrowed[1])}", "--json"],
            "reject",
            "common metric",
        ),
    ]
    env = {**os.environ, "NO_COLOR": "1"}
    env.pop("PYTHONPATH", None)
    if args.src:
        env["PYTHONPATH"] = str(args.src.resolve())
    results = []
    for label, command, expected, message in cases:
        process = subprocess.run(
            [args.python, "-m", "errorbars.cli", *command],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(process.stdout) if process.returncode == 0 else None
        if expected == "reject":
            passed = process.returncode == 1 and process.stdout == "" and message in process.stderr
        elif expected == "equal":
            passed = (
                process.returncode == 0
                and payload["mean_diff"] == 0
                and payload["inference"]["p_value"] == 1
                and payload["n"] == 24
            )
        else:
            model = "sshleifer/tiny-gpt2" if expected == "tiny" else "explicit"
            passed = process.returncode == 0 and payload["model"] == model and payload["mean"] == 0.6
        results.append(
            {
                "case": label,
                "command": ["errorbars", *command],
                "expected": expected,
                "matches_expected": passed,
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        )
    inputs = [arc, tiny, random_result, exact, folded, *narrowed, mixed, renamed]
    result = {
        "capture_check": (
            "24 identical documents, targets, responses and score values; only metrics order differs"
        ),
        "inputs": [{"path": rel(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],
        "cases": results,
        "disagreements": sum(not row["matches_expected"] for row in results),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(results)} CLI cases; {result['disagreements']} disagreements with corrected behavior")
    if result["disagreements"] and not args.observe_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
