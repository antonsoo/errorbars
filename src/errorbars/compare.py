"""Paired comparisons between two models on the same questions."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike

from errorbars._validation import group_vector, sample_sd, score_vector
from errorbars.stats import (
    cluster_degrees_of_freedom,
    cluster_robust_se,
    is_binary,
    t_for_confidence,
    t_two_sided_p,
)

__all__ = [
    "PairedComparison", "paired_compare", "McNemarResult", "mcnemar_exact",
    "SelectedInference", "select_inference", "PairedTest",
]

PairedTest = Literal["paired_t", "clustered_t", "mcnemar_exact"]


@dataclass(frozen=True)
class SelectedInference:
    """The test selected from observation structure, with its matching interval.

    Exact McNemar does not supply a mean-difference interval here. A paired-t
    interval must not be presented as the confidence interval of that test.
    The low-level PairedComparison retains all diagnostic calculations.
    """
    test: PairedTest
    p_value: float
    ci_low: float | None
    ci_high: float | None
    confidence: float | None
    mcnemar_applicable: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_inference(
    comparison: PairedComparison, *, single_observation_per_question: bool,
) -> SelectedInference:
    """Select from shared observations: clustered t, exact binary, then paired t.

    The caller must check generation counts on shared questions. A binary
    question mean can average many observations and is not a Bernoulli trial.
    """
    comp = comparison
    binary = comp.mcnemar is not None and single_observation_per_question
    if comp.p_value_clustered is not None:
        return SelectedInference(
            "clustered_t", comp.p_value_clustered, comp.ci_low_clustered,
            comp.ci_high_clustered, comp.confidence, binary,
        )
    if binary:
        assert comp.mcnemar is not None
        return SelectedInference("mcnemar_exact", comp.mcnemar.p_value, None, None, None, True)
    return SelectedInference("paired_t", comp.p_value, comp.ci_low, comp.ci_high, comp.confidence, False)

# Below this many effective degrees of freedom a 95% t interval is more than 13%
# wider than a normal one, and a reader should know why.
FEW_CLUSTER_DOF = 10.0


@dataclass(frozen=True)
class PairedComparison:
    """Result of a paired comparison between model A and model B."""

    mean_a: float
    mean_b: float
    mean_diff: float
    se_paired: float
    ci_low: float
    ci_high: float
    p_value: float
    correlation: float | None
    se_unpaired: float
    variance_reduction: float | None
    n: int
    confidence: float
    se_clustered: float | None = None
    ci_low_clustered: float | None = None
    ci_high_clustered: float | None = None
    p_value_clustered: float | None = None
    dof_clustered: float | None = None
    n_clusters: int | None = None
    mcnemar: McNemarResult | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "mean_a": self.mean_a,
            "mean_b": self.mean_b,
            "mean_diff": self.mean_diff,
            "se_paired": self.se_paired,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "p_value": self.p_value,
            "correlation": self.correlation,
            "se_unpaired": self.se_unpaired,
            "variance_reduction": self.variance_reduction,
            "n": self.n,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }
        if self.se_clustered is not None:
            d["se_clustered"] = self.se_clustered
            d["ci_low_clustered"] = self.ci_low_clustered
            d["ci_high_clustered"] = self.ci_high_clustered
            d["p_value_clustered"] = self.p_value_clustered
            d["dof_clustered"] = self.dof_clustered
            d["n_clusters"] = self.n_clusters
        if self.mcnemar is not None:
            d["mcnemar"] = self.mcnemar.as_dict()
        return d


def paired_compare(
    scores_a: ArrayLike,
    scores_b: ArrayLike,
    clusters: ArrayLike | None = None,
    confidence: float = 0.95,
) -> PairedComparison:
    """Paired difference test: mean(A) - mean(B) over the same questions.

    Reports the standard paired t-test SE/CI/p-value (Student t, n - 1
    degrees of freedom), the correlation between the two models'
    per-question scores, and how much pairing shrank the SE relative to an
    unpaired (independent two-sample) SE at the same n. When ``clusters`` is
    given, also reports a cluster-robust paired SE/CI/p-value: the
    bias-reduced CR2 estimator on t with Satterthwaite degrees of freedom
    (``errorbars.stats.cluster_robust_se``, ``cluster_degrees_of_freedom``).
    With equal cluster sizes that is the classic CR1 estimator on t(G - 1)
    (Cameron & Miller 2015); with unequal sizes it has fewer degrees of
    freedom and keeps its error rate, where CR1 does not. When both score
    vectors are binary, also runs McNemar's exact test.

    ``correlation`` is unavailable (None) when either vector is constant;
    ``variance_reduction`` is unavailable when both are constant. Warnings
    explain unavailable diagnostics and zero-variance t-test conventions.
    """
    a = score_vector(scores_a, "scores_a")
    b = score_vector(scores_b, "scores_b")
    if a.shape != b.shape:
        raise ValueError("scores_a and scores_b must have the same length (paired)")
    n = a.size
    if n < 2:
        raise ValueError("need at least 2 paired observations")

    diff = a - b
    mean_diff = float(diff.mean())
    sd_diff = sample_sd(diff)
    se_paired = sd_diff / math.sqrt(n)
    t_crit = t_for_confidence(confidence, n - 1)
    ci_low, ci_high = mean_diff - t_crit * se_paired, mean_diff + t_crit * se_paired
    p_value = _difference_p(mean_diff, se_paired, n - 1)
    notes = []
    if se_paired == 0:
        notes.append(
            "Paired differences have zero estimated variance. The t-test uses p=0 for a "
            "nonzero difference and p=1 for identical scores by convention; a point interval "
            "does not establish population certainty. Use the exact McNemar result for binary pairs."
        )

    sd_a, sd_b = sample_sd(a), sample_sd(b)
    scale_a, scale_b = float(np.max(np.abs(a))), float(np.max(np.abs(b)))
    corr = float(np.corrcoef(a / scale_a, b / scale_b)[0, 1]) if sd_a > 0 and sd_b > 0 else None
    if corr is None:
        notes.append("Correlation is unavailable because at least one score vector is constant.")
    se_unpaired = math.hypot(sd_a, sd_b) / math.sqrt(n)
    variance_reduction = 1.0 - (se_paired / se_unpaired) ** 2 if se_unpaired > 0 else None
    if variance_reduction is None:
        notes.append("Variance reduction is unavailable because both score vectors are constant.")

    se_clustered: float | None = None
    ci_low_c: float | None = None
    ci_high_c: float | None = None
    p_value_c: float | None = None
    dof_c: float | None = None
    n_clusters: int | None = None
    if clusters is not None:
        cluster_arr = group_vector(clusters, n)
        se_clustered = cluster_robust_se(diff, cluster_arr)
        sizes: dict[Any, int] = {}
        for cluster in cluster_arr.tolist():
            sizes[cluster] = sizes.get(cluster, 0) + 1
        n_clusters = len(sizes)
        dof_c = cluster_degrees_of_freedom(cluster_arr)
        t_crit_c = t_for_confidence(confidence, dof_c)
        ci_low_c = mean_diff - t_crit_c * se_clustered
        ci_high_c = mean_diff + t_crit_c * se_clustered
        p_value_c = _difference_p(mean_diff, se_clustered, dof_c)
        if se_clustered == 0:
            notes.append("Cluster sums have zero estimated variance; the clustered t-test is degenerate.")
        if dof_c < FEW_CLUSTER_DOF:
            notes.append(
                f"Clustered inference rests on {dof_c:.1f} effective degrees of freedom: "
                f"{n_clusters} clusters, the largest holding {max(sizes.values()) / n:.0%} of the "
                "questions. Its interval is wide because few independent clusters carry the estimate."
            )

    scores_list_a: list[float] = a.tolist()
    scores_list_b: list[float] = b.tolist()
    mcnemar = mcnemar_exact(scores_list_a, scores_list_b) if is_binary(a) and is_binary(b) else None

    return PairedComparison(
        mean_a=float(a.mean()),
        mean_b=float(b.mean()),
        mean_diff=mean_diff,
        se_paired=se_paired,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=float(p_value),
        correlation=corr,
        se_unpaired=se_unpaired,
        variance_reduction=variance_reduction,
        n=n,
        confidence=confidence,
        se_clustered=se_clustered,
        ci_low_clustered=ci_low_c,
        ci_high_clustered=ci_high_c,
        p_value_clustered=p_value_c,
        dof_clustered=dof_c,
        n_clusters=n_clusters,
        mcnemar=mcnemar,
        warnings=notes,
    )


def _difference_p(mean: float, se: float, dof: float) -> float:
    if se == 0:
        return 0.0 if mean != 0 else 1.0
    return t_two_sided_p(mean / se, dof)


@dataclass(frozen=True)
class McNemarResult:
    """Exact McNemar test on discordant pairs of a 2x2 paired-binary table."""

    n01: int  # A wrong, B right
    n10: int  # A right, B wrong
    p_value: float

    def as_dict(self) -> dict[str, Any]:
        return {"n01": self.n01, "n10": self.n10, "p_value": self.p_value}


def mcnemar_exact(scores_a: ArrayLike, scores_b: ArrayLike) -> McNemarResult:
    """Exact (binomial) two-sided McNemar test for paired binary outcomes.

    Uses only the discordant pairs b = #(A=0,B=1), c = #(A=1,B=0); under the
    null they are Binomial(b+c, 0.5). Reference: McNemar (1947); the exact
    version is preferred over the chi-square approximation when b+c is
    small. Matches ``statsmodels.stats.contingency_tables.mcnemar(...,
    exact=True)``.
    """
    a = score_vector(scores_a, "scores_a")
    b = score_vector(scores_b, "scores_b")
    if a.shape != b.shape:
        raise ValueError("scores_a and scores_b must have the same length (paired)")
    if not a.size or not is_binary(a) or not is_binary(b):
        raise ValueError("McNemar requires nonempty paired binary (exactly 0/1) scores")
    n01 = int(np.sum((a == 0) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    total = n01 + n10
    if total == 0:
        return McNemarResult(n01, n10, 1.0)
    k = min(n01, n10)
    if 2 * k >= total - 1:
        return McNemarResult(n01, n10, 1.0)
    # two-sided exact binomial test, p=0.5: sum both tails via symmetry
    # Adjacent coefficients obey C(n,i)=C(n,i-1)*(n-i+1)/i. Keep the
    # numerator exact, without rebuilding thousands of factorial ratios.
    coefficient = numerator = 1
    for i in range(1, k + 1):
        coefficient = coefficient * (total - i + 1) // i
        numerator += coefficient
    tail = numerator / (2**total)
    p_value = min(1.0, 2 * tail)
    return McNemarResult(n01, n10, float(p_value))
