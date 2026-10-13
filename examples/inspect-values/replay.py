"""Verify retained named Inspect scores through the library, CLI and canonical CSV.

Run with an installed errorbars interpreter. Numerical oracles use scipy;
artifact verification may use --without-scipy with the retained oracle receipt.
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
from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.io import concat, load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import write_comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parent


def replay(output: Path, without_scipy: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "logs/manifest.json").read_text())
    observed = {}
    for name, metadata in manifest["runs"].items():
        path = ROOT / f"logs/{name}.eval"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]
        log = read_eval_log(path)
        observed[name] = {}
        for sample in log.samples:
            answer = sample.output.completion.strip()
            expected = {"correct": "C" if answer == sample.target else "I",
                        "concise": len(answer.split()) <= 2, "words": len(answer.split())}
            assert sample.scores["answer_dimensions"].value == expected
            observed[name][sample.id, str(sample.epoch)] = expected
    evidence = {"synthetic": True, "version": errorbars.__version__, "cases": {}}
    specs = [f"A={ROOT / 'logs/baseline.eval'}", f"B={ROOT / 'logs/candidate.eval'}"]
    for key in ("correct", "concise", "words"):
        data = load_inputs(specs, score_key=key).data
        arrays = []
        for model, name in (("A", "baseline"), ("B", "candidate")):
            part = data.filter_model(model)
            expected = [observed[name][q, epoch][key]
                        for q, epoch in zip(part.question_id, part.sample, strict=True)]
            expected = [float(value == "C") if isinstance(value, str) else float(value) for value in expected]
            assert part.score == expected
            by_question = dict(zip(part.question_id, expected, strict=True))
            arrays.append([by_question[q] for q in sorted(by_question)])
        review = review_comparison(data, "A", "B")
        assert review.cohort["n_scoring_matching"] == 24
        assert review.cohort["n_identity_matching"] == 24
        expected_delta = math.fsum(a - b for a, b in zip(*arrays, strict=True)) / 24
        assert math.isclose(review.comparison.mean_diff, expected_delta)
        inference = review.inference
        if not without_scipy:
            from scipy.stats import binomtest, ttest_rel
            if key in ("correct", "concise"):
                discordant = [(a, b) for a, b in zip(*arrays, strict=True) if a != b]
                expected_p = binomtest(sum(a > b for a, b in discordant), len(discordant)).pvalue
            else:
                expected_p = float(ttest_rel(*arrays).pvalue)
            assert math.isclose(inference.p_value, expected_p, rel_tol=1e-10)
        else:
            expected_p = json.loads((ROOT / "evidence/after.json").read_text())["cases"][key]["oracle_p"]
            assert math.isclose(inference.p_value, expected_p, rel_tol=1e-10)
        write_comparison_html(review, output / f"{key}.html")
        (output / f"{key}.json").write_text(json.dumps(review.as_dict(), indent=2) + "\n")
        canonical = output / f"{key}.csv"
        write_csv(data, canonical)
        restored = load_csv(canonical)
        assert restored.scoring == data.scoring
        assert review_comparison(restored, "A", "B").comparison.as_dict() == review.comparison.as_dict()
        build_leaderboard(data)
        commands = [
            ["summarize", str(ROOT / "logs/baseline.eval"), "--score-key", key],
            ["compare", *specs, "--score-key", key], ["compare", str(canonical)],
            ["leaderboard", *specs, "--score-key", key],
        ]
        for args in commands:
            result = subprocess.run([sys.executable, "-m", "errorbars.cli", *args, "--json"],
                                    capture_output=True, text=True, check=False)
            assert result.returncode == 0, result.stderr
            payload = json.loads(result.stdout)
            assert {row["scorer_value"] for row in payload["score_values"]} == {key}
        evidence["cases"][key] = {"n": 24, "means": [math.fsum(a) / 24 for a in arrays],
                                  "difference": expected_delta, "inference": inference.as_dict(),
                                  "oracle_p": expected_p, "canonicalPreservesSelection": True,
                                  "cliCommandsPassed": len(commands)}
    a = load_inspect_log(ROOT / "logs/baseline.eval", score_key="correct")
    b = load_inspect_log(ROOT / "logs/candidate.eval", score_key="concise")
    a.model = ["A"] * len(a)
    b.model = ["B"] * len(b)
    conflict = concat([("a", a), ("b", b)])
    review = review_comparison(conflict, "A", "B")
    assert review.comparison is None and review.cohort["n_scoring_conflicting"] == 24
    write_comparison_html(review, output / "conflict.html")
    (output / "conflict.json").write_text(json.dumps(review.as_dict(), indent=2) + "\n")
    canonical = output / "conflict.csv"
    write_csv(conflict, canonical)
    for command in ("compare", "leaderboard"):
        result = subprocess.run([sys.executable, "-m", "errorbars.cli", command, str(canonical), "--json"],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 1 and "conflicting scoring rules" in result.stderr and not result.stdout
    evidence["conflict"] = {"scorer": "answer_dimensions", "values": ["correct", "concise"],
                            "conflictingQuestions": 24, "inferenceAvailable": False,
                            "canonicalCompareExit": 1, "canonicalLeaderboardExit": 1}
    epochs = load_inspect_log(ROOT / "logs/candidate-epochs.eval", score_key="correct")
    assert len(epochs) == 48 and len(epochs.scores_by_question()) == 24
    assert set(epochs.sample) == {"1", "2"}
    result = subprocess.run([sys.executable, "-m", "errorbars.cli", "summarize",
                             str(ROOT / "logs/candidate-epochs.eval"), "--score-key", "correct", "--json"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["n_questions"] == 24 and summary["n_observations"] == 48
    evidence["epochs"] = summary
    package = Path(errorbars.__file__).parent
    evidence["implementationSha256"] = {
        str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*")) if path.suffix in (".py", ".html", ".css", ".js")
    }
    (output / "observations.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"cases": evidence["cases"], "conflict": evidence["conflict"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--without-scipy", action="store_true")
    args = parser.parse_args()
    replay(args.output, args.without_scipy)
