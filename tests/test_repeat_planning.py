"""Planning counterexamples: extra answers do not replace independent questions."""

from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction

import numpy as np
import pytest
from scipy.stats import norm

from errorbars.power import minimum_detectable_effect, per_question_variance, questions_needed


@pytest.mark.parametrize("k", [1, 2, 4, 100])
@pytest.mark.parametrize("correlation", [0, 1 / 3, 0.8, 1])
def test_question_mean_variance_matches_full_covariance_matrix(k: int, correlation: float) -> None:
    # Sum the variances AND every cross-covariance of k draws, independently
    # of the planner's random-effects shortcut. This also covers the diagonal.
    covariance = np.full((k, k), 0.25 * correlation)
    np.fill_diagonal(covariance, 0.25)
    weights = np.full(k, 1 / k)
    expected_variance = float(weights @ covariance @ weights)
    inputs = dict(baseline_accuracy=0.5, samples_per_question=k, repeat_correlation=correlation)
    assert per_question_variance(**inputs) == pytest.approx(expected_variance, rel=1e-12)
    expected_n = np.ceil((norm.isf(0.025) + norm.ppf(0.8)) ** 2 * 2 * expected_variance / 0.05**2)
    assert questions_needed(0.05, **inputs).n_questions == expected_n
    expected_mde = (norm.isf(0.025) + norm.ppf(0.8)) * np.sqrt(2 * expected_variance / 500)
    assert minimum_detectable_effect(500, **inputs) == pytest.approx(expected_mde, rel=1e-12)


@pytest.mark.parametrize("k", [1, 2, 4, 6, 100])
def test_uniform_question_difficulty_matches_miller_section_3_1(k: int) -> None:
    # Integrals for p ~ U[0,1]: Var(p)=1/12 and E[p(1-p)]=1/6.
    # These are population components, not estimates computed by errorbars.
    expected = Fraction(1, 12) + Fraction(1, 6 * k)
    assert per_question_variance(0.5, samples_per_question=k, repeat_correlation=1 / 3) == pytest.approx(
        float(expected)
    )


def test_identical_repeats_never_reduce_the_required_questions() -> None:
    base = questions_needed(0.05, baseline_accuracy=0.5)
    assert base.n_questions == 1570
    for k in [2, 10, 100, 2**53 - 1]:
        result = questions_needed(0.05, baseline_accuracy=0.5, samples_per_question=k, repeat_correlation=1)
        assert result.n_questions == base.n_questions
        assert result.per_question_variance == base.per_question_variance


def test_unknown_repeat_dependence_has_no_implicit_independence_default() -> None:
    with pytest.raises(ValueError, match="repeat_correlation is required"):
        per_question_variance(0.5, samples_per_question=2)
    with pytest.raises(ValueError, match="repeat_correlation is required"):
        questions_needed(0.05, baseline_accuracy=0.5, samples_per_question=2)
    with pytest.raises(ValueError, match="repeat_correlation is required"):
        minimum_detectable_effect(500, baseline_accuracy=0.5, samples_per_question=2)
    assert questions_needed(0.05, baseline_accuracy=0.5).as_dict()["repeat_correlation"] is None


@pytest.mark.parametrize("r", [-0.01, 1.01, float("nan"), float("inf"), True])
@pytest.mark.parametrize("k", [1, 4])
def test_invalid_repeat_assumptions_are_rejected_even_for_single_answers(r: float, k: int) -> None:
    inputs = dict(variance=1.0, repeat_correlation=r, samples_per_question=k)
    with pytest.raises(ValueError, match="repeat_correlation must be"):
        questions_needed(0.05, **inputs)
    with pytest.raises(ValueError, match="repeat_correlation must be"):
        minimum_detectable_effect(500, **inputs)


@pytest.mark.parametrize("k", [2, 10, 100])
def test_repeats_preserve_a_positive_variance_floor_and_inverse_plan(k: int) -> None:
    inputs = dict(variance=0.25, samples_per_question=k, repeat_correlation=0.8, rho=0.3)
    v = per_question_variance(variance=0.25, samples_per_question=k, repeat_correlation=0.8)
    assert 0.2 < v < 0.25
    mde = minimum_detectable_effect(500, **inputs)
    assert questions_needed(mde, **inputs).n_questions in (500, 501)


@pytest.mark.parametrize("direction", [["--delta", "0.05"], ["--n", "500"]])
def test_cli_requires_and_retains_repeat_assumptions(direction: list[str]) -> None:
    command = [
        sys.executable,
        "-m",
        "errorbars.cli",
        "power",
        *direction,
        "--baseline",
        "0.5",
        "--samples-per-question",
        "100",
    ]
    refused = subprocess.run([*command, "--json"], capture_output=True, text=True)
    assert refused.returncode != 0 and refused.stdout == ""
    assert "--repeat-correlation" in refused.stderr
    accepted = subprocess.run(
        [*command, "--repeat-correlation", "0.8", "--json"], capture_output=True, text=True, check=True
    )
    payload = json.loads(accepted.stdout)
    assert payload["repeat_correlation"] == 0.8
    if "--delta" in direction:
        assert payload["n_questions"] == 1259
    else:
        assert payload["mde"] == pytest.approx((norm.isf(0.025) + norm.ppf(0.8)) * (0.401 / 500) ** 0.5)
    terminal = subprocess.run(
        [*command, "--repeat-correlation", "0.8"], capture_output=True, text=True, check=True
    )
    assert "Repeat correlation 0.8" in terminal.stdout
