"""Power analysis for paired LLM eval comparisons.

Model: each question contributes a score whose single-sample variance is
``p*(1-p)`` for a binary metric (or a user-supplied ``variance`` for a
continuous one). With repeat correlation r, averaging k generations gives
variance ``V * (r + (1-r)/k)``: the between-question component does not
disappear with more answers. For k > 1, r must be supplied explicitly.
Pairing two models on the same questions with correlation ``rho`` between
their k-generation question means
shrinks the variance of the difference to ``2*V*(1-rho)`` relative to
``2*V`` for an unpaired design. Clustering of questions (e.g. several
questions per passage) inflates that further by the Kish design effect.

This is a standard normal-approximation power formula (e.g. Fleiss,
Levin & Paik, "Statistical Methods for Rates and Proportions", 3rd ed.,
ch. 3) generalized with the pairing and clustering factors above.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any

__all__ = [
    "PowerResult", "questions_needed", "minimum_detectable_effect", "per_question_variance",
    "BinaryEffectRange", "BinaryFeasibilityError", "binary_effect_range",
]

_NORMAL = NormalDist()
_MAX_COUNT = 2**53 - 1  # Keep plans exactly representable in the browser as well as Python.


class BinaryFeasibilityError(ValueError):
    """The requested binary comparison cannot exist under its pairing assumptions."""


@dataclass(frozen=True)
class BinaryEffectRange:
    """Feasible positive mean improvements for two single Bernoulli outcomes.

    Zero is always excluded. A zero-correlation upper endpoint is also excluded:
    a target that is always correct has no defined Pearson correlation.
    """

    minimum_delta: float
    maximum_delta: float
    maximum_inclusive: bool

    def as_dict(self) -> dict[str, float | bool | str]:
        return {
            "model": "single-answer-bernoulli",
            "minimum_delta": self.minimum_delta,
            "maximum_delta": self.maximum_delta,
            "minimum_inclusive": self.minimum_delta > 0,
            "maximum_inclusive": self.maximum_inclusive,
        }

    def describe(self) -> str:
        lower = "greater than 0" if self.minimum_delta == 0 else f"at least {100 * self.minimum_delta:.8g}"
        upper = "at most" if self.maximum_inclusive else "less than"
        return f"{lower} and {upper} {100 * self.maximum_delta:.8g} percentage points"

    def contains(self, delta: float) -> bool:
        # Tolerance is relative to the effect, not to the baseline: an absolute
        # epsilon could admit a materially impossible gap near perfect pairing.
        tolerance = 16 * math.ulp(1.0) * max(abs(delta), abs(self.minimum_delta))
        upper_tolerance = 16 * math.ulp(1.0) * max(abs(delta), abs(self.maximum_delta))
        return (
            math.isfinite(delta) and delta > 0
            and delta >= self.minimum_delta - tolerance
            and (delta <= self.maximum_delta + upper_tolerance if self.maximum_inclusive
                 else delta < self.maximum_delta)
        )


def binary_effect_range(baseline_accuracy: float, rho: float) -> BinaryEffectRange:
    """The positive-effect interval allowed by nonnegative cells in a 2x2 table.

    For baseline p and target q, P(A=1,B=1) = pq + rho*sqrt(p(1-p)q(1-q)).
    Requiring all four cells to be nonnegative bounds q at fixed p and rho.
    This checks feasibility, not the calibration of the normal power formula.
    It does not apply to averages of multiple answers or continuous scores.
    """
    if not 0 < baseline_accuracy < 1:
        raise ValueError("baseline_accuracy must be strictly between 0 and 1")
    if not -1 <= rho <= 1:
        raise ValueError("rho must be in [-1, 1]")
    p = baseline_accuracy
    complement = 1 - p
    r = abs(rho)
    if rho >= 0:
        low = 0.0
        # Factored forms avoid subtracting nearly equal q and p at rho near 1.
        high = (
            complement if rho == 0
            else p * complement * (1 - r) * (1 + r) / (p + r * r * complement)
        )
    else:
        low = max(0.0, (r * complement - p) * (r * complement + p) / (p + r * r * complement))
        high = (complement - r * p) * (complement + r * p) / (complement + r * r * p)
    if high <= 0 or low > high:
        raise BinaryFeasibilityError(
            "This baseline and correlation permit no positive improvement for single-answer "
            "binary scores. Change the assumed correlation or baseline."
        )
    return BinaryEffectRange(low, high, rho != 0 and p + high < 1)


def _check_binary_delta(baseline: float, delta: float, bounds: BinaryEffectRange) -> None:
    if baseline + delta >= 1 or not bounds.contains(delta):
        raise BinaryFeasibilityError(
            f"The assumed correlation permits binary improvements {bounds.describe()}; "
            f"the requested gap is {100 * delta:.8g} points. Change the correlation or gap."
        )


def _check_count(value: int, name: str, minimum: int) -> None:
    if isinstance(value, bool) or not minimum <= value <= _MAX_COUNT or int(value) != value:
        raise ValueError(f"{name} must be an integer from {minimum} to {_MAX_COUNT}")


def per_question_variance(
    baseline_accuracy: float | None = None,
    variance: float | None = None,
    samples_per_question: int = 1,
    *,
    repeat_correlation: float | None = None,
) -> float:
    """Per-question score variance after averaging repeated samples.

    Exactly one of ``baseline_accuracy`` (binary metric, variance =
    p(1-p)) or ``variance`` (continuous metric, raw per-sample variance)
    must be given. ``repeat_correlation`` is the within-question correlation
    between two draws from the same model, assumed common to both models.
    Under conditionally independent generation, it equals the fraction of
    single-draw variance attributable to question difficulty. It must be in
    [0, 1] and is required when averaging more than one generation. Zero is
    an explicit independence assumption; one gives no benefit from repeats.
    """
    if (baseline_accuracy is None) == (variance is None):
        raise ValueError("pass exactly one of baseline_accuracy or variance")
    _check_count(samples_per_question, "samples_per_question", 1)
    if baseline_accuracy is not None and not 0.0 < baseline_accuracy < 1.0:
        # p(1-p) is 0 at either end, which would make any gap look free to detect.
        raise ValueError(f"baseline_accuracy must be strictly between 0 and 1, got {baseline_accuracy}")
    if variance is not None and not (variance > 0 and math.isfinite(variance)):
        raise ValueError(f"variance must be a positive, finite number, got {variance}")
    if repeat_correlation is not None and (
        isinstance(repeat_correlation, bool) or not 0.0 <= repeat_correlation <= 1.0
    ):
        raise ValueError(f"repeat_correlation must be a finite number in [0, 1], got {repeat_correlation}")
    if samples_per_question > 1 and repeat_correlation is None:
        raise ValueError(
            "repeat_correlation is required for samples_per_question > 1 "
            "(CLI: --repeat-correlation). Use 0 only to assume independent repeats, "
            "or 1 to assume no variance reduction from repeats."
        )
    v = baseline_accuracy * (1 - baseline_accuracy) if baseline_accuracy is not None else variance
    assert v is not None
    r = repeat_correlation if repeat_correlation is not None else 0.0
    result = v if samples_per_question == 1 else v * (r + (1 - r) / samples_per_question)
    if result <= 0:
        raise ValueError("per-question variance is too small to represent")
    return result


@dataclass(frozen=True)
class PowerResult:
    n_questions: int
    delta: float
    alpha: float
    power: float
    rho: float
    samples_per_question: int
    cluster_design_effect: float
    per_question_variance: float
    repeat_correlation: float | None = None
    binary_feasibility: BinaryEffectRange | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_questions": self.n_questions,
            "delta": self.delta,
            "alpha": self.alpha,
            "power": self.power,
            "rho": self.rho,
            "samples_per_question": self.samples_per_question,
            "cluster_design_effect": self.cluster_design_effect,
            "per_question_variance": self.per_question_variance,
            "repeat_correlation": self.repeat_correlation,
            "binary_feasibility": self.binary_feasibility.as_dict() if self.binary_feasibility else None,
        }


def _z_beta(power: float) -> float:
    if not 0.0 < power < 1.0:
        raise ValueError(f"power must be in (0, 1), got {power}")
    return _NORMAL.inv_cdf(power)  # one-sided: z such that Phi(z) = power


def _z_alpha(alpha: float) -> float:
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if alpha / 2 == 0:
        raise ValueError("alpha is too small to represent its two-sided tail")
    return -_NORMAL.inv_cdf(alpha / 2)


def _z_sum(alpha: float, power: float) -> float:
    result = _z_alpha(alpha) + _z_beta(power)
    if result <= 0:
        raise ValueError("power is too low for this positive-effect approximation at the given alpha")
    return result


def _difference_sd(v: float, rho: float, cluster_design_effect: float) -> float:
    # Take roots before multiplying: finite factors can overflow or underflow as a variance.
    return math.sqrt(v) * math.sqrt(2 * (1 - rho)) * math.sqrt(cluster_design_effect)


def _check_design(rho: float, cluster_design_effect: float) -> None:
    if not -1.0 <= rho <= 1.0:
        raise ValueError(f"rho must be in [-1, 1], got {rho}")
    if not (cluster_design_effect >= 1.0 and math.isfinite(cluster_design_effect)):
        raise ValueError(f"cluster_design_effect must be a finite number >= 1, got {cluster_design_effect}")


def questions_needed(
    delta: float,
    baseline_accuracy: float | None = None,
    variance: float | None = None,
    alpha: float = 0.05,
    power: float = 0.8,
    rho: float = 0.0,
    samples_per_question: int = 1,
    cluster_design_effect: float = 1.0,
    *,
    repeat_correlation: float | None = None,
) -> PowerResult:
    """Number of questions needed to detect a paired mean difference ``delta``.

    ``n = (z_{a/2} + z_b)^2 * 2*V*(1-rho) * deff / delta^2`` where V is the
    per-question variance (see ``per_question_variance``).
    ``rho`` describes the two models' question means at the requested repeat
    count; it may change when the count changes. It is distinct from
    ``repeat_correlation``, which describes draws from one model.
    """
    if not (delta > 0 and math.isfinite(delta)):
        raise ValueError(f"delta must be a positive, finite number, got {delta}")
    _check_design(rho, cluster_design_effect)
    v = per_question_variance(
        baseline_accuracy, variance, samples_per_question, repeat_correlation=repeat_correlation
    )
    if baseline_accuracy is not None and baseline_accuracy + delta > 1.0:
        raise ValueError(
            f"baseline_accuracy + delta = {baseline_accuracy + delta:.3g}: an accuracy can't exceed 1"
        )
    z = _z_sum(alpha, power)
    bounds = None
    if baseline_accuracy is not None and samples_per_question == 1:
        bounds = binary_effect_range(baseline_accuracy, rho)
        _check_binary_delta(baseline_accuracy, delta, bounds)
    root_n = _difference_sd(v, rho, cluster_design_effect) / delta * z
    if not math.isfinite(root_n) or root_n > math.sqrt(_MAX_COUNT):
        raise ValueError("required question count exceeds the exactly representable planning range")
    n_int = max(2, math.ceil(root_n * root_n))
    _check_count(n_int, "required question count", 2)
    return PowerResult(
        n_int, delta, alpha, power, rho, samples_per_question, cluster_design_effect, v,
        repeat_correlation, bounds,
    )


def minimum_detectable_effect(
    n_questions: int,
    baseline_accuracy: float | None = None,
    variance: float | None = None,
    alpha: float = 0.05,
    power: float = 0.8,
    rho: float = 0.0,
    samples_per_question: int = 1,
    cluster_design_effect: float = 1.0,
    *,
    repeat_correlation: float | None = None,
) -> float:
    """Smallest feasible paired difference detectable with a given n, alpha, power.

    For a single binary answer, intersect the normal approximation's detectable
    effects with the joint Bernoulli interval. Negative correlation can impose a
    positive minimum gap even at infinite budget. Raise BinaryFeasibilityError
    when the interval contains no detectable effect; never return an impossible
    binary gap. Continuous and repeated-average designs keep their variance model.
    """
    _check_count(n_questions, "n_questions", 2)
    _check_design(rho, cluster_design_effect)
    v = per_question_variance(
        baseline_accuracy, variance, samples_per_question, repeat_correlation=repeat_correlation
    )
    z = _z_sum(alpha, power)
    result = _difference_sd(v, rho, cluster_design_effect) / math.sqrt(n_questions) * z
    if not math.isfinite(result) or (result == 0 and rho != 1):
        raise ValueError("minimum detectable effect is outside the representable planning range")
    if baseline_accuracy is not None and samples_per_question == 1:
        bounds = binary_effect_range(baseline_accuracy, rho)
        result = max(result, bounds.minimum_delta)
        if baseline_accuracy + result >= 1 or not bounds.contains(result):
            raise BinaryFeasibilityError(
                "This budget cannot detect a feasible binary improvement at the requested power. "
                f"The assumed correlation permits gaps {bounds.describe()}. "
                "Increase the budget or change the planning assumptions."
            )
        result = min(result, bounds.maximum_delta)
    return result
