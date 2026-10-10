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

__all__ = ["PowerResult", "questions_needed", "minimum_detectable_effect", "per_question_variance"]

_NORMAL = NormalDist()
_MAX_COUNT = 2**53 - 1  # Keep plans exactly representable in the browser as well as Python.


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
    root_n = _difference_sd(v, rho, cluster_design_effect) / delta * z
    if not math.isfinite(root_n) or root_n > math.sqrt(_MAX_COUNT):
        raise ValueError("required question count exceeds the exactly representable planning range")
    n_int = max(2, math.ceil(root_n * root_n))
    _check_count(n_int, "required question count", 2)
    return PowerResult(
        n_int, delta, alpha, power, rho, samples_per_question, cluster_design_effect, v, repeat_correlation
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
    """Smallest paired difference detectable with a given n, alpha, power."""
    _check_count(n_questions, "n_questions", 2)
    _check_design(rho, cluster_design_effect)
    v = per_question_variance(
        baseline_accuracy, variance, samples_per_question, repeat_correlation=repeat_correlation
    )
    z = _z_sum(alpha, power)
    result = _difference_sd(v, rho, cluster_design_effect) / math.sqrt(n_questions) * z
    if not math.isfinite(result) or (result == 0 and rho != 1):
        raise ValueError("minimum detectable effect is outside the representable planning range")
    return result
