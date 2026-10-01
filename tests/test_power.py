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
        f"n={result.n_questions} gave empirical power {empirical_power:.3f}, "
        f"target was {target_power}"
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

