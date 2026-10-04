"""Power formulas checked by simulation and by internal consistency."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pytest

from errorbars.power import minimum_detectable_effect, per_question_variance, questions_needed

_NORMAL = NormalDist()


def _simulate_paired_power(
    n: int, variance: float, rho: float, delta: float, alpha: float, trials: int, seed: int
) -> float:
    """Empirical power of the paired z-test on simulated correlated normal scores."""
    rng = np.random.default_rng(seed)
    cov = np.array([[variance, rho * variance], [rho * variance, variance]])
    z_crit = _NORMAL.inv_cdf(1 - alpha / 2)
    rejections = 0
    for _ in range(trials):
        samples = rng.multivariate_normal([0.0, delta], cov, size=n)
        diff = samples[:, 1] - samples[:, 0]
        se = diff.std(ddof=1) / np.sqrt(n)
        z = diff.mean() / se if se > 0 else 0.0
        rejections += abs(z) > z_crit
    return rejections / trials


@pytest.mark.parametrize(
    "variance,rho,delta,target_power",
    [
        (1.0, 0.0, 0.5, 0.8),
        (1.0, 0.5, 0.4, 0.8),
        (0.25, 0.3, 0.25, 0.9),
    ],
)
def test_questions_needed_achieves_target_power_by_simulation(
    variance: float, rho: float, delta: float, target_power: float
) -> None:
    result = questions_needed(delta=delta, variance=variance, alpha=0.05, power=target_power, rho=rho)
    empirical_power = _simulate_paired_power(
        result.n_questions, variance, rho, delta, alpha=0.05, trials=3000, seed=42
    )
    assert abs(empirical_power - target_power) < 0.05, (
        f"n={result.n_questions} gave empirical power {empirical_power:.3f}, target was {target_power}"
    )


def test_minimum_detectable_effect_is_inverse_of_questions_needed() -> None:
    n = 400
    mde = minimum_detectable_effect(n_questions=n, variance=1.0, alpha=0.05, power=0.8, rho=0.2)
    back = questions_needed(delta=mde, variance=1.0, alpha=0.05, power=0.8, rho=0.2)
    # ceil() rounding means back.n_questions should be n or n-1 (mde solves n exactly).
    assert back.n_questions in (n, n - 1, n + 1)


def test_questions_needed_scales_linearly_with_cluster_design_effect() -> None:
    base = questions_needed(delta=0.05, baseline_accuracy=0.5, cluster_design_effect=1.0)
    doubled = questions_needed(delta=0.05, baseline_accuracy=0.5, cluster_design_effect=2.0)
    assert doubled.n_questions == pytest.approx(2 * base.n_questions, rel=0.02)


def test_questions_needed_scales_inversely_with_samples_per_question() -> None:
    base = questions_needed(delta=0.05, baseline_accuracy=0.5, samples_per_question=1)
    quadrupled_samples = questions_needed(delta=0.05, baseline_accuracy=0.5, samples_per_question=4)
    assert quadrupled_samples.n_questions == pytest.approx(base.n_questions / 4, rel=0.05)


def test_higher_correlation_reduces_questions_needed() -> None:
    low_rho = questions_needed(delta=0.05, baseline_accuracy=0.5, rho=0.0)
    high_rho = questions_needed(delta=0.05, baseline_accuracy=0.5, rho=0.8)
    assert high_rho.n_questions < low_rho.n_questions


def test_per_question_variance_requires_exactly_one_input() -> None:
    with pytest.raises(ValueError):
        per_question_variance()
    with pytest.raises(ValueError):
        per_question_variance(baseline_accuracy=0.5, variance=0.2)


def test_questions_needed_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        questions_needed(delta=0.0, baseline_accuracy=0.5)
    with pytest.raises(ValueError):
        questions_needed(delta=0.05, baseline_accuracy=0.5, rho=1.5)
    with pytest.raises(ValueError):
        questions_needed(delta=0.05, baseline_accuracy=0.5, cluster_design_effect=0.5)


@pytest.mark.parametrize("baseline", [0.0, 1.0, -0.1, 1.2])
def test_baseline_must_be_strictly_inside_zero_one(baseline: float) -> None:
    # p(1-p) = 0 at either end would make any gap look free to detect ("2 questions needed").
    with pytest.raises(ValueError, match="strictly between 0 and 1"):
        questions_needed(0.05, baseline_accuracy=baseline)


def test_a_target_accuracy_above_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="an accuracy can't exceed 1"):
        questions_needed(0.05, baseline_accuracy=0.98)


def test_variance_must_be_positive() -> None:
    with pytest.raises(ValueError, match="variance must be a positive"):
        questions_needed(0.05, variance=0.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"delta": float("nan"), "variance": 0.2}, "delta must be a positive, finite number"),
        ({"delta": float("inf"), "variance": 0.2}, "delta must be a positive, finite number"),
        ({"delta": 0.05, "variance": float("inf")}, "variance must be a positive, finite number"),
        ({"delta": 0.05, "variance": 0.2, "alpha": 0.0}, "alpha must be in"),
        ({"delta": 0.05, "variance": 0.2, "alpha": float("nan")}, "alpha must be in"),
        ({"delta": 0.05, "variance": 0.2, "rho": float("nan")}, "rho must be in"),
        ({"delta": 0.05, "variance": 0.2, "cluster_design_effect": float("nan")}, "cluster_design_effect"),
        ({"delta": 0.05, "variance": 0.2, "cluster_design_effect": float("inf")}, "cluster_design_effect"),
    ],
)
def test_questions_needed_rejects_arguments_with_no_answer(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        questions_needed(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rho": 2.0}, "rho must be in"),
        ({"rho": float("nan")}, "rho must be in"),
        ({"cluster_design_effect": 0.5}, "cluster_design_effect"),
        ({"cluster_design_effect": float("nan")}, "cluster_design_effect"),
        ({"alpha": 1.0}, "alpha must be in"),
    ],
)
def test_mde_checks_the_design_the_way_questions_needed_does(kwargs: dict, message: str) -> None:
    # rho=2 used to surface as "math domain error", and a design effect below 1 was accepted.
    with pytest.raises(ValueError, match=message):
        minimum_detectable_effect(200, variance=0.2, **kwargs)


@pytest.mark.parametrize("count", [True, 2.5, float("nan"), float("inf"), 2**53, -1, 0])
def test_planning_counts_are_finite_exact_integers(count: int) -> None:
    with pytest.raises(ValueError, match="integer"):
        minimum_detectable_effect(count, baseline_accuracy=0.5)
    with pytest.raises(ValueError, match="integer"):
        questions_needed(0.03, baseline_accuracy=0.5, samples_per_question=count)


def test_low_power_cannot_produce_a_negative_detectable_effect() -> None:
    for operation in [
        lambda: minimum_detectable_effect(500, baseline_accuracy=0.5, power=0.001),
        lambda: questions_needed(0.03, baseline_accuracy=0.5, power=0.001),
    ]:
        with pytest.raises(ValueError, match="power is too low"):
            operation()


def test_unrepresentable_question_count_has_an_actionable_error() -> None:
    with pytest.raises(ValueError, match="representable planning range"):
        questions_needed(1e-200, baseline_accuracy=0.5)


def test_tiny_alpha_uses_the_lower_tail_without_subtraction_cancellation() -> None:
    from scipy.stats import norm

    expected = (norm.isf(1e-30 / 2) + norm.ppf(0.8)) * (0.5 / 500) ** 0.5
    assert minimum_detectable_effect(500, baseline_accuracy=0.5, alpha=1e-30) == pytest.approx(expected)


def test_large_finite_variance_does_not_overflow_before_taking_its_root() -> None:
    mde = minimum_detectable_effect(100, variance=1e308)
    assert mde == pytest.approx((_NORMAL.inv_cdf(0.975) + _NORMAL.inv_cdf(0.8)) * (2**0.5) * 1e153)


@pytest.mark.parametrize("n", [2, 500, 10_000_000])
@pytest.mark.parametrize("baseline,rho,deff", [(0.001, -0.95, 1), (0.5, 0.3, 2.9), (0.999, 0.95, 1000)])
def test_mde_against_independent_scipy_quantiles(n: int, baseline: float, rho: float, deff: float) -> None:
    from scipy.stats import norm

    expected = (norm.isf(0.01 / 2) + norm.ppf(0.99)) * (
        2 * baseline * (1 - baseline) * (1 - rho) * deff / n
    ) ** 0.5
    actual = minimum_detectable_effect(
        n, baseline_accuracy=baseline, rho=rho, cluster_design_effect=deff, alpha=0.01, power=0.99
    )
    assert actual == pytest.approx(expected, rel=1e-13)


def test_committed_web_vectors_match_the_current_python_formulas() -> None:
    import json
    from pathlib import Path

    vectors = json.loads((Path(__file__).parents[1] / "web/test-vectors.json").read_text())
    for case in vectors["normalQuantiles"]:
        assert _NORMAL.inv_cdf(case["p"]) == pytest.approx(case["z"], rel=1e-14, abs=1e-14)
    for section in ["questionsNeeded", "minimumDetectableEffect"]:
        cases = vectors[section]
        for case in cases:
            source = case["inputs"]
            kwargs = dict(
                baseline_accuracy=source["baseline"],
                alpha=source["alpha"],
                power=source["power"],
                rho=source["rho"],
                samples_per_question=source["samplesPerQuestion"],
                cluster_design_effect=source["clusterDeff"],
            )
            if section == "questionsNeeded":
                result = questions_needed(source["delta"], **kwargs)
                assert result.n_questions == case["nQuestions"], case
                assert result.per_question_variance == pytest.approx(case["perQuestionVariance"], rel=1e-12)
            else:
                result_mde = minimum_detectable_effect(source["n"], **kwargs)
                assert result_mde == pytest.approx(case["mde"], rel=1e-12), case
    # Guard against truncating the beginning of a Cartesian product again.
    assert len({c["inputs"]["baseline"] for c in vectors["questionsNeeded"]}) == 6
    assert len({c["inputs"]["n"] for c in vectors["minimumDetectableEffect"]}) == 7
