"""Generate reports used by real browser workflows; no model or network calls."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from errorbars.inputs import load_inputs
from errorbars.io import EvalData, ScoringRule, load_csv
from errorbars.report import write_comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    capture = load_inputs([ROOT / "tests/fixtures/lm_eval_output"]).data
    real = review_comparison(capture, "hf-internal-testing/tiny-random-gpt2", "sshleifer/tiny-gpt2")
    write_comparison_html(real, output / "copa.html")
    clustered = review_comparison(
        load_csv(ROOT / "examples/data/reading_comprehension.csv"), "tuned-70b", "baseline-70b"
    )
    write_comparison_html(clustered, output / "clustered.html")
    for name, filename in (("two-wins", "two-questions.csv"), ("binary-repeats", "repeated.csv")):
        data = load_csv(ROOT / "examples/leaderboard-tests" / filename)
        a, b = data.models()
        write_comparison_html(review_comparison(data, a, b), output / f"{name}.html")

    path = output / "partial-synthetic.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "model", "score", "cluster_id", "sample"])
        for model, indices in [("A", range(125)), ("B", range(5, 135))]:
            for i in indices:
                repeats = 151 if i == 5 and model == "A" else 1
                for sample in range(repeats):
                    score = (i % 5) / 5 + (0.1 if model == "A" else 0)
                    if repeats > 1:
                        score = (sample % 7) / 7
                    writer.writerow([f"q{i:03d}", model, score, f"group-{i // 5:02d}", sample])
    write_comparison_html(review_comparison(load_csv(path), "A", "B"), output / "partial.html")

    model = '</script><script>window.pwned=true</script>\u202e'
    ids = ['=SUM(1,2)', '<img src="https://example.invalid/leak" onerror="window.pwned=true">',
           'tab\tand\nnewline', "q3", "q4"]
    hostile = EvalData(ids * 2, [model] * len(ids) + ["B"] * len(ids), [1, 0, .5, 0, 1, 0, 1, .1, 1, 0])
    write_comparison_html(review_comparison(hostile, model, "B"), output / "hostile.html")

    source = next((ROOT / "tests/fixtures/lm_eval_output/sshleifer__tiny-gpt2").glob("samples_*.jsonl"))
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    rows[0]["doc"]["premise"] = "A different question with the same id."
    changed = output / source.name
    changed.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    conflict = load_inputs([f"original={source}", f"changed={changed}"]).data
    write_comparison_html(review_comparison(conflict, "original", "changed"), output / "conflict.html")
    scoring_conflict = EvalData(
        ["q1", "q2"] * 2, ["A", "A", "B", "B"], [0, 1, 1, 1],
        question_hash=["same-q1", "same-q2"] * 2,
        scoring=[ScoringRule("inspect:match", "exact")] * 2 + [ScoringRule("inspect:match", "any")] * 2,
    )
    write_comparison_html(review_comparison(scoring_conflict, "A", "B"), output / "scoring-conflict.html")
    missing = EvalData(["a", "b", "x", "y"], ["A", "A", "B", "B"], [1, 0, 0, 1])
    write_comparison_html(review_comparison(missing, "A", "B"), output / "missing.html")

    n = 12000
    ids = [f"question-{i:05d}" for i in range(n)]
    scores_a = [float(i % 5 != 0) for i in range(n)]
    scores_b = [float(i % 7 != 0) for i in range(n)]
    large = EvalData(ids * 2, ["A"] * n + ["B"] * n, scores_a + scores_b)
    write_comparison_html(review_comparison(large, "A", "B"), output / "large.html")
    print(f"Generated comparison reports in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
