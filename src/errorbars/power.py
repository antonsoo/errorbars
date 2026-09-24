"""Power analysis for paired LLM eval comparisons.

Model: each question contributes a score whose single-sample variance is
``p*(1-p)`` for a binary metric (or a user-supplied ``variance`` for a
continuous one). Averaging ``samples_per_question`` repeated generations
per question reduces that variance by a factor of ``samples_per_question``
(we do not assume a separate item-difficulty/decoding-noise split for
planning purposes — see docs/formulas.md for the rationale and how this
differs from the post-hoc decomposition in ``summarize``). Pairing two
models on the same questions with per-question score correlation ``rho``
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

from errorbars.stats import z_for_confidence

__all__ = ["PowerResult", "questions_needed", "minimum_detectable_effect", "per_question_variance"]

_NORMAL = NormalDist()


def per_question_variance(
    baseline_accuracy: float | None = None,
    variance: float | None = None,
    samples_per_question: int = 1,
) -> float:
    """Per-question score variance after averaging repeated samples.

    Exactly one of ``baseline_accuracy`` (binary metric, variance =
    p(1-p)) or ``variance`` (continuous metric, raw per-sample variance)
    must be given.
    """
    if (baseline_accuracy is None) == (variance is None):
        raise ValueError("pass exactly one of baseline_accuracy or variance")
    if samples_per_question < 1:
        raise ValueError("samples_per_question must be >= 1")
    v = baseline_accuracy * (1 - baseline_accuracy) if baseline_accuracy is not None else variance
    return v / samples_per_question  # type: ignore[operator]


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
        }


def _z_beta(power: float) -> float:
    if not 0.0 < power < 1.0:
        raise ValueError(f"power must be in (0, 1), got {power}")
    return _NORMAL.inv_cdf(power)  # one-sided: z such that Phi(z) = power


def questions_needed(
    delta: float,
    baseline_accuracy: float | None = None,
    variance: float | None = None,
    alpha: float = 0.05,
    power: float = 0.8,
    rho: float = 0.0,
    samples_per_question: int = 1,
    cluster_design_effect: float = 1.0,
) -> PowerResult:
    """Number of questions needed to detect a paired mean difference ``delta``.

    ``n = (z_{a/2} + z_b)^2 * 2*V*(1-rho) * deff / delta^2`` where V is the
    per-question variance (see ``per_question_variance``).
    """
    if delta <= 0:
        raise ValueError("delta must be positive")
    if not -1.0 <= rho <= 1.0:
        raise ValueError("rho must be in [-1, 1]")
    if cluster_design_effect < 1.0:
        raise ValueError("cluster_design_effect must be >= 1")
    v = per_question_variance(baseline_accuracy, variance, samples_per_question)
    z_a = z_for_confidence(1 - alpha)
    z_b = _z_beta(power)
    n = ((z_a + z_b) ** 2) * 2 * v * (1 - rho) * cluster_design_effect / (delta**2)
    n_int = max(2, math.ceil(n))
    return PowerResult(n_int, delta, alpha, power, rho, samples_per_question, cluster_design_effect, v)


def minimum_detectable_effect(
    n_questions: int,
    baseline_accuracy: float | None = None,
    variance: float | None = None,
    alpha: float = 0.05,
    power: float = 0.8,
    rho: float = 0.0,
    samples_per_question: int = 1,
    cluster_design_effect: float = 1.0,
) -> float:
    """Smallest paired difference detectable with a given n, alpha, power."""
    if n_questions < 2:
        raise ValueError("n_questions must be >= 2")
    v = per_question_variance(baseline_accuracy, variance, samples_per_question)
    z_a = z_for_confidence(1 - alpha)
    z_b = _z_beta(power)
    return (z_a + z_b) * math.sqrt(2 * v * (1 - rho) * cluster_design_effect / n_questions)
