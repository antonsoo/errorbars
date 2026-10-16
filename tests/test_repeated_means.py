"""Changing a repetition count must not create a model gain from rounding."""

from __future__ import annotations

import itertools
import math
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard
from errorbars.review import review_comparison


def _data(values: dict[str, list[float]]) -> EvalData:
    rows = [
        (str(q), model, score, str(sample))
        for model, scores in values.items()
        for q in range(20)
        for sample, score in enumerate(scores)
    ]
    return EvalData(
        question_id=[row[0] for row in rows],
        model=[row[1] for row in rows],
        score=[row[2] for row in rows],
        sample=[row[3] for row in rows],
    )


@pytest.mark.parametrize("value", [0.1, 0.3, -0.1, 1e-30, 1e100])
def test_identical_grades_keep_the_same_question_mean_for_any_repetition_count(value):
    for count in (1, 3, 10, 99):
        means = _data({"model": [value] * count}).scores_by_question()
        assert set(means.values()) == {value}


@pytest.mark.parametrize(
    "values", [[0.1, 0.2], [1e16, 1.0, -1e16], [1e100, 1.0, -1e100], [1e-300, 2e-300, -1e-300]]
)
def test_question_mean_matches_exact_input_ratios_under_reordering_and_repetition(values):
    expected = float(sum((Fraction.from_float(value) for value in values), Fraction()) / len(values))
    for reordered in itertools.permutations(values):
        for count in (1, 3, 10):
            means = _data({"model": list(reordered) * count}).scores_by_question()
            assert set(means.values()) == {expected}


def test_identical_raw_grades_form_one_group_without_significant_pairs():
    board = build_leaderboard(_data({"once": [0.1], "triple": [0.1] * 3, "ten": [0.1] * 10}))
    assert len(board.groups) == 1 and set(board.groups[0]) == {"once", "triple", "ten"}
    assert all(pair.comparison.mean_diff == 0 and pair.p_holm == 1 for pair in board.pairwise)
    review = review_comparison(_data({"once": [0.1], "triple": [0.1] * 3}), "once", "triple")
    assert review.comparison is not None
    assert review.comparison.mean_diff == 0 and review.inference.p_value == 1
    assert all(question.difference == 0 for question in review.questions)


def test_real_single_ulp_difference_is_retained_without_a_significance_tolerance():
    a, b = 0.1, math.nextafter(0.1, math.inf)
    board = build_leaderboard(_data({"a": [a], "b": [b] * 3}))
    pair = board.pairwise[0]
    assert pair.comparison.mean_diff == (b - a if pair.model_a == "b" else a - b)
    # Keep the existing degenerate t-test convention and its explicit warning.
    assert pair.p_holm == 0 and any("zero estimated variance" in note for note in pair.comparison.warnings)


def test_numpy_integer_grades_are_averaged_in_score_units():
    data = _data({"model": [np.int64(0), np.int64(1)]})
    assert set(data.scores_by_question().values()) == {0.5}


def test_actual_inspect_epochs_do_not_manufacture_a_paired_gain():
    pytest.importorskip("inspect_ai")
    from errorbars.inputs import load_inputs

    fixtures = Path(__file__).resolve().parents[1] / "studies/repeated-means/fixtures"
    data = load_inputs([f"once={fixtures / 'epochs-1.eval'}", f"triple={fixtures / 'epochs-3.eval'}"]).data
    assert len(data) == 80 and set(data.score) == {0.1}
    review = review_comparison(data, "once", "triple")
    assert review.comparison is not None and review.comparison.n == 20
    assert review.comparison.mean_diff == 0 and review.inference.p_value == 1
    assert all(question.identity == "matching" for question in review.questions)
