"""Audit native recorded reducers against closed-form authored outcomes and real CLI.

Run this script with the old or repaired package on PYTHONPATH. Retained .eval
files are read using Inspect itself, never reconstructed from our adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import subprocess
import sys
from pathlib import Path

from inspect_ai.log import read_eval_log
from inspect_ai.scorer import value_to_float

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.io import load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import write_comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ROOT / "studies/inspect-reducers/captures"


def run(output, artifacts, check):
    artifacts.mkdir(parents=True, exist_ok=True)
    cases = [(name, None, None) for name in
             ("mean", "none", "max", "pass_at_2", "median", "mode", "at_least_2", "mean-max")]
    cases += [("mean-max", reducer, None) for reducer in ("mean", "max")]
    cases += [("named-max", None, key) for key in ("correct", "loss")]
    supported = "inspect_reducer" in inspect.signature(load_inspect_log).parameters
    rows, files = [], {}
    for label, requested, key in cases:
        case = "-".join(str(x) for x in (label, requested, key) if x is not None)
        specs = [f"{profile}={CAPTURES.relative_to(ROOT) / (label + '-' + profile + '.eval')}"
                 for profile in ("broad", "concentrated")]
        for profile in ("broad", "concentrated"):
            path = CAPTURES / f"{label}-{profile}.eval"
            files[path.name] = {"bytes": path.stat().st_size,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        options = {"score_key": key} if key is not None else {}
        flags = ["--score-key", key] if key is not None else []
        if requested is not None:
            options["inspect_reducer"] = requested
            flags += ["--inspect-reducer", requested]
        # Exact authored probability: of 3 draws with one success, selecting
        # two without replacement succeeds with probability 1-C(2,2)/C(3,2).
        reducer = requested or ("max" if label == "named-max" else label)
        expected_a = {"mean": 1 / 3, "none": 1 / 3, "max": 1,
                      "pass_at_2": 1 - math.comb(2, 2) / math.comb(3, 2),
                      "median": 0, "mode": 0, "at_least_2": 0}.get(reducer)
        expected_b = .25 if key == "loss" else .75
        result = {"case": case, "native_reducer": reducer, "expected_a": expected_a,
                  "expected_b": expected_b, "requested": requested, "score_key": key}
        if requested is not None and not supported:
            result["status"] = "selector unavailable in baseline"
            rows.append(result)
            continue
        try:
            data = load_inputs(specs, **options).data
            review = review_comparison(data, "broad", "concentrated")
            result.update(status="loaded", observations=len(data),
                          mean_a=review.comparison.mean_a, mean_b=review.comparison.mean_b,
                          difference=review.comparison.mean_diff,
                          test=review.inference.test, p=review.inference.p_value,
                          ranking=[entry.model for entry in build_leaderboard(data).entries],
                          score_values=review.score_values)
            if check:
                assert expected_a is not None, "ambiguous multi-reducer input was silently selected"
                assert math.isclose(result["mean_a"], expected_a, abs_tol=1e-15)
                assert result["mean_b"] == expected_b
                expected_n = 144 if reducer in ("mean", "none") else 48
                assert len(data) == expected_n
                if expected_n == 48:
                    assert data.sample is None
                    for profile in ("broad", "concentrated"):
                        native = read_eval_log(CAPTURES / f"{label}-{profile}.eval")
                        scorer = "named_grade" if key is not None else "match"
                        selected = next(v for v in native.reductions
                                        if v.reducer == reducer and v.scorer == scorer)
                        convert = value_to_float()
                        expected = {str(s.sample_id): convert(s.value[key] if key else s.value)
                                    for s in selected.samples}
                        assert data.filter_model(profile).scores_by_question() == expected
            canonical = artifacts / f"{case}.csv"
            write_csv(data, canonical)
            restored = load_csv(canonical)
            assert restored.score == data.score and restored.scoring == data.scoring
            restored_review = review_comparison(restored, "broad", "concentrated")
            assert restored_review.comparison.as_dict() == review.comparison.as_dict()
            assert restored_review.inference == review.inference
            write_comparison_html(review, artifacts / f"{case}.html")
            write_comparison_html(restored_review, artifacts / f"{case}-roundtrip.html")
        except ValueError as exc:
            result.update(status="refused", error=str(exc))
            if check:
                assert label == "mean-max" and requested is None, result
        commands = []
        for command in ("summarize", "compare", "leaderboard", "import"):
            suffix = {"compare": "html", "leaderboard": "svg"}.get(command, "csv")
            target = artifacts / f"{case}-cli.{suffix}"
            args = [command, *specs, *flags, "--json"]
            if command == "summarize":
                args += ["--model", "broad"]
            elif command == "import":
                args = [command, "inspect", *specs, *flags, "-o", str(target)]
            else:
                args += ["--html" if command == "compare" else "--plot", str(target)]
            if result["status"] == "refused":
                target.write_bytes(b"preserve previous result\n")
            invocation = subprocess.run([sys.executable, "-m", "errorbars.cli", *args],
                                        cwd=ROOT, capture_output=True, text=True)
            if check:
                assert invocation.returncode == (1 if result["status"] == "refused" else 0), invocation.stderr
                assert "Traceback" not in invocation.stderr
                if result["status"] == "refused":
                    assert not invocation.stdout and target.read_bytes() == b"preserve previous result\n"
                elif command in ("summarize", "compare", "leaderboard"):
                    report = json.loads(invocation.stdout)
                    assert report.get("score_values"), "selected score definition was omitted"
            commands.append({"command": command, "exit": invocation.returncode,
                             "stdout": invocation.stdout, "stderr": invocation.stderr})
        result["cli"] = commands
        rows.append(result)
    receipt = {"python": sys.version, "package": __import__("errorbars").__file__,
               "synthetic": True, "questions": 24, "epochs": 3,
               "files": files, "cases": rows, "checked": check}
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"cases": len(rows), "commands": sum(len(r.get("cli", [])) for r in rows),
                      "checked": check}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    run(args.out, args.artifacts, args.check)
