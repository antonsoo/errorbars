"""Primary conclusions must follow observation structure in every interface."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_cli import run_cli

from errorbars.io import EvalData, load_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]


def test_two_wins_headline_exact_p_half_not_the_degenerate_t_diagnostic(tmp_path: Path) -> None:
    path = ROOT / "examples/leaderboard-tests/two-questions.csv"
    html = tmp_path / "two.html"
    result = run_cli("compare", str(path), "--json", "--html", str(html))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["p_value"] == 0  # Backward-compatible low-level t diagnostic.
    assert payload["inference"] == {
        "test": "mcnemar_exact",
        "p_value": 0.5,
        "ci_low": None,
        "ci_high": None,
        "confidence": None,
        "mcnemar_applicable": True,
    }
    text = html.read_text()
    headline = re.search(r'<p id="inference-description">(.*?)</p>', text).group(1)
    assert "Exact McNemar p = 0.5000" in headline
    assert "No significant difference detected" in headline
    assert "CI" not in headline and "p = 0.0000" not in headline
    assert "Paired t (diagnostic)" in text
    assert "No exact mean-difference interval is supplied" in text
    terminal = run_cli("compare", str(path)).stdout
    assert "selected test" in terminal and "McNemar exact" in terminal
    assert "paired-t p-value (diagnostic)" in terminal


@pytest.mark.parametrize("repeated", [False, True])
@pytest.mark.parametrize("clustered", [False, True])
def test_shared_selection_policy_and_matching_interval(repeated: bool, clustered: bool) -> None:
    qids = ["q1", "q2", "q3", "q4"]
    a, b = [1.0, 1.0, 0.0, 1.0], [0.0, 1.0, 0.0, 0.0]
    copies = 2 if repeated else 1
    data = EvalData(
        (qids * copies) * 2,
        ["a"] * (4 * copies) + ["b"] * (4 * copies),
        a * copies + b * copies,
        (["c1", "c1", "c2", "c2"] * copies) * 2 if clustered else None,
        (sum(([str(i)] * 4 for i in range(copies)), [])) * 2,
    )
    review = review_comparison(data, "a", "b", confidence=0.9)
    selected = review.inference
    assert selected is not None
    expected = "clustered_t" if clustered else "paired_t" if repeated else "mcnemar_exact"
    assert selected.test == expected
    assert selected.mcnemar_applicable is not repeated
    pair = build_leaderboard(data, confidence=0.9).pairwise[0]
    assert pair.test == selected.test
    assert pair.p_value_used == selected.p_value
    if expected == "mcnemar_exact":
        assert selected.ci_low is selected.ci_high is selected.confidence is None
    else:
        assert selected.confidence == 0.9
        assert selected.ci_low <= review.comparison.mean_diff <= selected.ci_high
    if repeated:
        # Binary repeated means retain the legacy diagnostic in JSON, but are
        # not described as exact Bernoulli trials in the rendered report.
        assert review.comparison.mcnemar is not None
        assert "Exact McNemar" not in comparison_html(review)


def test_unmatched_repeats_do_not_change_shared_binary_inference() -> None:
    data = EvalData(
        ["q1", "q2", "q3", "q3", "q1", "q2"],
        ["a"] * 4 + ["b"] * 2,
        [1.0] * 4 + [0.0] * 2,
        sample=["0", "0", "0", "1", "0", "0"],
    )
    inference = review_comparison(data, "a", "b").inference
    assert inference.test == "mcnemar_exact"
    assert inference.p_value == 0.5


def test_unavailable_cohort_does_not_acquire_a_selected_test() -> None:
    data = EvalData(["a", "b", "x", "y"], ["A", "A", "B", "B"], [1.0, 0.0, 0.0, 1.0])
    review = review_comparison(data, "A", "B")
    assert review.inference is None
    assert review.as_dict()["inference"] is None


def test_continuous_scores_keep_the_paired_t_interval() -> None:
    data = load_csv(ROOT / "examples/data/reading_comprehension.csv")
    data.cluster_id = None
    data.score = [score * 0.9 for score in data.score]
    review = review_comparison(data, "tuned-70b", "baseline-70b")
    selected = review.inference
    assert selected.test == "paired_t"
    assert selected.ci_low == review.comparison.ci_low
    assert selected.ci_high == review.comparison.ci_high
    assert not selected.mcnemar_applicable
