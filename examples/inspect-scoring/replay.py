"""Replay retained Inspect captures with the installed Errorbars implementation.

    uv run python examples/inspect-scoring/replay.py OUTPUT_DIRECTORY --expect-repaired

Omit --expect-repaired to measure an older checkout on these exact same bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

from inspect_ai.log import read_eval_log

import errorbars
from errorbars.inputs import load_inputs
from errorbars.io import load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import write_comparison_html
from errorbars.review import review_comparison

LOGS = Path(__file__).resolve().parent / "logs"


def replay(output: Path, expect_repaired: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((LOGS / "manifest.json").read_text())
    logs = {}
    for name, record in manifest["runs"].items():
        path = LOGS / f"{name}.eval"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        logs[name] = {s.id: s for s in read_eval_log(path).samples}
        # Independently evaluate these unambiguous synthetic answers as text.
        for sample in logs[name].values():
            exact = sample.output.completion.strip() == sample.target
            contains = sample.target in sample.output.completion
            observed = next(iter(sample.scores.values())).value == "C"
            assert observed == (contains if name in ("anywhere", "includes") else exact)

    package = Path(errorbars.__file__).parent
    implementation = {
        path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*")) if path.suffix in (".py", ".js", ".html", ".css")
    }
    evidence = {
        "synthetic": True, "version": errorbars.__version__, "implementation_sha256": implementation,
        "inputs": {name: record["sha256"] for name, record in manifest["runs"].items()},
        "comparisons": {},
    }
    print("case             same answers  native inference  CSV inference  CLI exits (native/CSV)")
    for name in ("anywhere", "includes", "exact-repeat", "improved-exact"):
        same_answers = all(logs["exact"][qid].output.completion == sample.output.completion
                           for qid, sample in logs[name].items())
        specs = [f"A={LOGS / 'exact.eval'}", f"B={LOGS / (name + '.eval')}"]
        data = load_inputs(specs).data
        review = review_comparison(data, "A", "B")
        write_comparison_html(review, output / f"{name}.html")
        csv = output / f"{name}.csv"
        write_csv(data, csv)
        restored = review_comparison(load_csv(csv), "A", "B")
        try:
            board = build_leaderboard(data)
            leaderboard = {"ranked": True, "models": [entry.model for entry in board.entries]}
        except ValueError as exc:
            leaderboard = {"ranked": False, "reason": str(exc)}
        cli = []
        for paths in (specs, [str(csv)]):
            result = subprocess.run(
                [sys.executable, "-m", "errorbars.cli", "compare", *paths, "--json"],
                capture_output=True, text=True, check=False,
            )
            cli.append({"exit": result.returncode, "stdout": json.loads(result.stdout)
                        if result.stdout else None, "stderr": result.stderr.strip()})
        summary = review.as_dict()
        case = {key: summary[key] for key in ("cohort", "comparison", "inference", "unavailable_reason")}
        case.update({
            "identical_responses": same_answers, "leaderboard": leaderboard, "cli": cli,
            "csv_cohort": restored.cohort, "csv_inference_available": restored.comparison is not None,
        })
        evidence["comparisons"][name] = case
        if expect_repaired:
            changed_rule = name in ("anywhere", "includes")
            assert same_answers == (name != "improved-exact")
            assert (review.comparison is None) == changed_rule
            assert (restored.comparison is None) == changed_rule
            assert review.cohort["n_identity_matching"] == 24
            assert review.cohort["n_scoring_conflicting"] == (24 if changed_rule else 0)
            assert leaderboard["ranked"] != changed_rule
            assert [result["exit"] for result in cli] == ([1, 1] if changed_rule else [0, 0])
            if not changed_rule:
                assert review.comparison.mean_diff == (0 if same_answers else -1 / 3)
                # Eight one-sided discordances in the improvement control.
                expected_p = 1.0 if same_answers else 2 * math.comb(8, 0) / 2**8
                assert review.inference.p_value == expected_p
        available = review.comparison is not None
        print(f"{name:16} {str(same_answers):>12}  {str(available):>16}  "
              f"{str(restored.comparison is not None):>13}  {cli[0]['exit']}/{cli[1]['exit']}")
    (output / "results.json").write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expect-repaired", action="store_true")
    args = parser.parse_args()
    replay(args.output, args.expect_repaired)
