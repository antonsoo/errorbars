"""One mean-selection policy for summaries and leaderboard entries.

Question averages are the observations. Supplied multi-question clusters select
CR2 uncertainty; an independent-question estimate remains a labelled diagnostic.
Insufficient independent units retain the mean without inventing an interval.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from errorbars._validation import group_vector, score_vector
from errorbars.compare import FEW_CLUSTER_DOF
from errorbars.stats import (
    MeanEstimate,
    bootstrap_ci,
    cluster_degrees_of_freedom,
    cluster_robust_se,
    is_binary,
    mean_ci_clt,
    prefer_wilson,
    t_for_confidence,
    wilson_ci,
)

IntervalStatus = Literal["available", "fewer_than_two_questions", "fewer_than_two_clusters"]
IndependentCI = Literal["auto", "clt", "wilson", "bootstrap"]


@dataclass(frozen=True)
class MeanSummary:
    mean: float
    se: float | None
    ci_low: float | None
    ci_high: float | None
    n: int
    method: str
    confidence: float
    interval_status: IntervalStatus = "available"
    n_clusters: int | None = None
    dof_clustered: float | None = None
    unclustered: MeanEstimate | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_mean(
    scores: list[float], *, repeated: bool = False, clusters: list[str] | None = None,
    confidence: float = 0.95, independent_method: IndependentCI = "auto",
    use_wilson_below_n: int | None = 30, seed: int | None = 0,
) -> MeanSummary:
    """Select uncertainty from actual question/group counts, retaining diagnostics.

    ``independent_method`` chooses the independent-question estimate. With
    multi-question clusters it cannot replace the primary CR2 interval. Repeated
    generation averages are not Bernoulli observations, even at zero or one.
    """
    values = score_vector(scores)
    n = values.size
    if n == 0:
        raise ValueError("need at least one question for a mean")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if independent_method not in ("auto", "clt", "wilson", "bootstrap"):
        raise ValueError(f"unsupported independent-question interval method: {independent_method!r}")
    binary = is_binary(values)
    if independent_method == "wilson" and (repeated or not binary):
        raise ValueError(
            "--ci wilson requires one binary (0/1) observation per question; "
            "repeated-generation averages are not binary trials"
        )
    use_wilson = independent_method == "wilson" or (
        independent_method == "auto" and not repeated and binary and use_wilson_below_n is not None
        and prefer_wilson(int(round(sum(scores))), n, below_n=use_wilson_below_n)
    )
    independent = None
    if use_wilson:
        independent = wilson_ci(int(round(sum(scores))), n, confidence)
    elif n >= 2:
        independent = (
            bootstrap_ci(scores, confidence=confidence, seed=seed)
            if independent_method == "bootstrap" else mean_ci_clt(scores, confidence)
        )

    cluster_count = None
    if clusters is not None:
        checked = group_vector(clusters, n)
        cluster_count = len(set(checked.tolist()))
    grouped = cluster_count is not None and cluster_count < n
    mean = independent.mean if independent is not None else math.fsum(scores) / n
    if grouped and cluster_count == 1:
        return MeanSummary(
            mean, None, None, None, n, "unavailable", confidence,
            interval_status="fewer_than_two_clusters", n_clusters=1, unclustered=independent,
            warnings=[
                "Only one independent cluster is observed; at least two are needed "
                "to estimate a clustered interval."
            ],
        )
    if independent is None:
        return MeanSummary(
            mean, None, None, None, n, "unavailable", confidence,
            interval_status="fewer_than_two_questions",
            warnings=[
                "Only one distinct question is observed; at least two are needed "
                "to estimate a mean interval for continuous or repeated-generation scores."
            ],
        )
    if not grouped:
        return MeanSummary(
            mean, independent.se, independent.ci_low, independent.ci_high, n,
            independent.method, confidence,
        )
    assert clusters is not None
    se = cluster_robust_se(scores, clusters)
    dof = cluster_degrees_of_freedom(clusters)
    half_width = t_for_confidence(confidence, dof) * se
    notes = []
    if dof < FEW_CLUSTER_DOF:
        notes.append(
            f"The interval uses {cluster_count} clusters and {dof:.1f} effective "
            "degrees of freedom; few independent clusters limit precision."
        )
    if se == 0:
        notes.append(
            "Cluster residual sums have zero estimated variance; "
            "a point interval does not establish population certainty."
        )
    return MeanSummary(
        mean, se, mean - half_width, mean + half_width, n, "clustered_cr2", confidence,
        n_clusters=cluster_count, dof_clustered=dof, unclustered=independent, warnings=notes,
    )
