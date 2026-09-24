"""Paired comparisons between two models on the same questions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from errorbars.stats import cluster_robust_se, is_binary, z_for_confidence

__all__ = ["PairedComparison", "paired_compare", "McNemarResult", "mcnemar_exact"]

_NORMAL = NormalDist()


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
    correlation: float
    se_unpaired: float
    variance_reduction: float
    n: int
    confidence: float
    se_clustered: float | None = None
    ci_low_clustered: float | None = None
    ci_high_clustered: float | None = None
    p_value_clustered: float | None = None
    mcnemar: McNemarResult | None = None

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
        }
        if self.se_clustered is not None:
            d["se_clustered"] = self.se_clustered
            d["ci_low_clustered"] = self.ci_low_clustered
            d["ci_high_clustered"] = self.ci_high_clustered
            d["p_value_clustered"] = self.p_value_clustered
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

    Reports the standard paired t-test SE/CI/p-value, the correlation
    between the two models' per-question scores, and how much pairing
    shrank the SE relative to an unpaired (independent two-sample) SE at
    the same n. When ``clusters`` is given, also reports a cluster-robust
    paired SE/CI (see ``errorbars.stats.cluster_robust_se``). When both
    score vectors are binary, also runs McNemar's exact test.
    """
    a = np.asarray(scores_a, dtype=float)
    b = np.asarray(scores_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("scores_a and scores_b must have the same length (paired)")
    n = a.size
    if n < 2:
        raise ValueError("need at least 2 paired observations")

    diff = a - b
    mean_diff = float(diff.mean())
    sd_diff = float(diff.std(ddof=1))
    se_paired = sd_diff / math.sqrt(n)
    z = z_for_confidence(confidence)
    ci_low, ci_high = mean_diff - z * se_paired, mean_diff + z * se_paired

    # two-sided p-value from the (large-sample) z statistic; for n<30 a
    # t-distribution is more exact, but we avoid a scipy runtime dependency
    # and instead use the normal approximation with a documented caveat.
    t_stat = mean_diff / se_paired if se_paired > 0 else 0.0
    p_value = 2 * (1 - _NORMAL.cdf(abs(t_stat)))

    var_a, var_b = float(a.var(ddof=1)), float(b.var(ddof=1))
    corr = float(np.corrcoef(a, b)[0, 1]) if var_a > 0 and var_b > 0 else 0.0
    var_unpaired = var_a + var_b
    se_unpaired = math.sqrt(var_unpaired / n)
    variance_reduction = 1.0 - (se_paired**2 / se_unpaired**2) if se_unpaired > 0 else 0.0

    se_clustered: float | None = None
    ci_low_c: float | None = None
    ci_high_c: float | None = None
    p_value_c: float | None = None
    if clusters is not None:
        se_clustered = cluster_robust_se(diff, np.asarray(clusters))
        ci_low_c = mean_diff - z * se_clustered
        ci_high_c = mean_diff + z * se_clustered
        t_stat_c = mean_diff / se_clustered if se_clustered > 0 else 0.0
        p_value_c = float(2 * (1 - _NORMAL.cdf(abs(t_stat_c))))

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
        variance_reduction=float(variance_reduction),
        n=n,
        confidence=confidence,
        se_clustered=se_clustered,
        ci_low_clustered=ci_low_c,
        ci_high_clustered=ci_high_c,
        p_value_clustered=p_value_c,
        mcnemar=mcnemar,
    )


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
    a = np.asarray(scores_a)
    b = np.asarray(scores_b)
    n01 = int(np.sum((a == 0) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    total = n01 + n10
    if total == 0:
        return McNemarResult(n01, n10, 1.0)
    k = min(n01, n10)
    # two-sided exact binomial test, p=0.5: sum both tails via symmetry
    tail = sum(math.comb(total, i) for i in range(0, k + 1)) / (2**total)
    p_value = min(1.0, 2 * tail)
    return McNemarResult(n01, n10, float(p_value))
