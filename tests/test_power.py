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
