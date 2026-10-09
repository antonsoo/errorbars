"""Replay retained synthetic Inspect runs through the installed Errorbars package.

Writes JSON evidence, offline comparison reports, and clearly labelled damaged
copies. Run with the same inputs under an older checkout to compare behavior.

    uv run python examples/inspect-comparison/replay.py OUTPUT_DIRECTORY
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inspect_ai.log import read_eval_log, write_eval_log

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.report import write_comparison_html
from errorbars.review import review_comparison

LOGS = Path(__file__).resolve().parent / "logs"


def replay(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"synthetic": True, "comparisons": {}, "damaged_logs": {}}
    for name in ("solver-variant", "different-questions", "limited", "selected-epochs"):
        data = load_inputs([f"A={LOGS / 'original.eval'}", f"B={LOGS / f'{name}.eval'}"]).data
        review = review_comparison(data, "A", "B")
        write_comparison_html(review, output / f"{name}.html")
        evidence["comparisons"][name] = {
            "cohort": review.cohort, "comparison": review.comparison.as_dict() if review.comparison else None,
            "unavailable_reason": review.unavailable_reason,
        }

    for damage in ("missing-records", "cancelled", "failed-samples", "mixed-scorers"):
        log = read_eval_log(LOGS / "original.eval")
        if damage == "missing-records":
            log.samples = log.samples[:8]
        elif damage == "cancelled":
            log.status = "cancelled"
        elif damage == "failed-samples":
            log.results.completed_samples = 8
        else:
            first = log.samples[0]
            first.scores = {"different_criterion": first.scores["match"]}
        path = output / f"damaged-{damage}.eval"
        write_eval_log(log, path)
        try:
            rows = load_inspect_log(path)
        except ValueError as exc:
            result = {"imported": None, "error": str(exc).replace(str(path), path.name)}
        else:
            result = {"imported": len(rows), "error": None}
        evidence["damaged_logs"][damage] = result
    (output / "results.json").write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")

    print("case                  paired n  matching  conflicts  outcome")
    for name, case in evidence["comparisons"].items():
        cohort, comparison = case["cohort"], case["comparison"]
        n = str(comparison["n"]) if comparison else "-"
        outcome = f"p={comparison['p_value']:.6g}" if comparison else "inference withheld"
        print(f"{name:21} {n:>8}  {cohort['n_identity_matching']:>8}  "
              f"{cohort['n_identity_conflicting']:>9}  {outcome}")
    print("\ndamaged copy          imported  outcome")
    for name, case in evidence["damaged_logs"].items():
        imported = str(case["imported"]) if case["imported"] is not None else "-"
        print(f"{name:21} {imported:>8}  {'refused' if case['error'] else 'accepted'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    replay(parser.parse_args().output)
