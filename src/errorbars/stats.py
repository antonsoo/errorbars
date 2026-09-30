"""Core statistics: means, confidence intervals, clustering diagnostics.

Formulas are derived from scratch (no scipy/statsmodels at runtime) and
cross-checked in ``tests/`` against statsmodels and scipy, which are used
only as test-time oracles. See ``docs/formulas.md`` for derivations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
from numpy.typing import ArrayLike

__all__ = [
    "MeanEstimate",
    "ClusterDiagnostics",
    "z_for_confidence",
    "mean_ci_clt",
    "wilson_ci",
    "bootstrap_ci",
    "cluster_robust_se",
    "intraclass_correlation",
    "design_effect",
    "within_between_variance",
    "is_binary",
    "t_two_sided_p",
    "t_for_confidence",
    "regularized_incomplete_beta",
]

_NORMAL = NormalDist()


def z_for_confidence(confidence: float) -> float:
    """Two-sided normal critical value, e.g. 1.959964 for 95% confidence."""
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    return _NORMAL.inv_cdf(0.5 + confidence / 2.0)


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function, evaluated with the
    modified Lentz method (Numerical Recipes, 3rd ed., section 6.4)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        even = m * (b - m) * x / ((qam + m2) * (a + m2))
        odd = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        for aa in (even, odd):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b), the regularized incomplete beta function, for a, b > 0."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    # The continued fraction converges fast for x < (a + 1) / (a + b + 2); use the
    # symmetry I_x(a, b) = 1 - I_{1-x}(b, a) on the other side.
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def t_two_sided_p(t_stat: float, dof: float) -> float:
    """Two-sided p-value of a Student-t statistic with `dof` degrees of
    freedom: P(|T| >= |t|) = I_{dof/(dof+t^2)}(dof/2, 1/2)."""
    if dof <= 0:
        raise ValueError("degrees of freedom must be positive")
    if math.isinf(t_stat):
        return 0.0
    return regularized_incomplete_beta(dof / 2.0, 0.5, dof / (dof + t_stat * t_stat))


def t_for_confidence(confidence: float, dof: float) -> float:
    """Two-sided Student-t critical value, e.g. 2.0227 for 95% with 39 degrees
    of freedom (1.96 as dof grows). Found by bisection on `t_two_sided_p`."""
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    alpha = 1.0 - confidence
    lo, hi = 0.0, max(10.0, z_for_confidence(confidence) * 4)
    while t_two_sided_p(hi, dof) > alpha:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_two_sided_p(mid, dof) > alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2.0


def is_binary(values: ArrayLike) -> bool:
    """True if every value is (close to) 0 or 1."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return False
    return bool(np.all((np.isclose(arr, 0.0)) | (np.isclose(arr, 1.0))))


@dataclass(frozen=True)
class MeanEstimate:
    """A point estimate of a mean with its uncertainty."""

    mean: float
    se: float
    ci_low: float
    ci_high: float
    confidence: float
    method: str
    n: int

    def as_dict(self) -> dict[str, float | str | int]:
        return {
            "mean": self.mean,
            "se": self.se,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "confidence": self.confidence,
            "method": self.method,
            "n": self.n,
        }


def mean_ci_clt(values: ArrayLike, confidence: float = 0.95) -> MeanEstimate:
    """CLT (Wald) confidence interval for a sample mean.

    SE = s / sqrt(n) using the sample standard deviation (ddof=1). This is
    the default estimator for continuous scores and for binary scores when
    n is reasonably large (see ``wilson_ci`` for the small-n binary case).
    """
    arr = np.asarray(values, dtype=float)
    n = arr.size
    if n < 2:
        raise ValueError("need at least 2 observations for a CLT interval")
    mean = float(arr.mean())
    se = float(arr.std(ddof=1) / np.sqrt(n))
    z = z_for_confidence(confidence)
    return MeanEstimate(mean, se, mean - z * se, mean + z * se, confidence, "clt", n)


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> MeanEstimate:
    """Wilson score interval for a binomial proportion.

    Preferred over the CLT/Wald interval for binary scores when n is small
    or the proportion is near 0/1, where the Wald interval can badly
    under-cover or extend outside [0, 1]. Reference: Wilson (1927),
    "Probable Inference, the Law of Succession, and Statistical Inference."
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    z = z_for_confidence(confidence)
    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    half_width = (z * np.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))) / denom
    se = float(np.sqrt(p_hat * (1 - p_hat) / n)) if 0 < p_hat < 1 else float(np.sqrt(z2) / (2 * n))
    return MeanEstimate(
        p_hat, se, float(center - half_width), float(center + half_width), confidence, "wilson", n
    )


def bootstrap_ci(
    values: ArrayLike,
    confidence: float = 0.95,
    n_boot: int = 10_000,
    seed: int | None = 0,
) -> MeanEstimate:
    """Percentile bootstrap confidence interval for the mean."""
    arr = np.asarray(values, dtype=float)
    n = arr.size
    if n < 2:
        raise ValueError("need at least 2 observations to bootstrap")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_means = arr[idx].mean(axis=1)
    alpha = 1 - confidence
    lo, hi = np.quantile(boot_means, [alpha / 2, 1 - alpha / 2])
    mean = float(arr.mean())
    se = float(boot_means.std(ddof=1))
    return MeanEstimate(mean, se, float(lo), float(hi), confidence, "bootstrap", n)


@dataclass(frozen=True)
class ClusterDiagnostics:
    """Design-effect diagnostics for clustered data."""

    icc: float
    avg_cluster_size: float
    n_clusters: int
    design_effect: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "icc": self.icc,
            "avg_cluster_size": self.avg_cluster_size,
            "n_clusters": self.n_clusters,
            "design_effect": self.design_effect,
        }


def _group_by(values: np.ndarray, clusters: np.ndarray) -> list[np.ndarray]:
    order = np.argsort(clusters, kind="stable")
    values_sorted = values[order]
    clusters_sorted = clusters[order]
    # np.diff doesn't support string/object dtypes; compare neighbors directly.
    boundaries = np.flatnonzero(clusters_sorted[1:] != clusters_sorted[:-1]) + 1
    return np.split(values_sorted, boundaries)


def intraclass_correlation(values: ArrayLike, clusters: ArrayLike) -> float:
    """One-way random-effects ANOVA estimate of the intraclass correlation.

    ICC = (MSB - MSW) / (MSB + (k0 - 1) * MSW), the classic Fisher/Kish
    estimator for clustered/panel data with possibly unequal cluster sizes
    (k0 is the harmonic-mean-like correction, Kish 1965 eq. 8.4.1).
    Returns 0.0 (no clustering signal) if there is only one cluster or all
    clusters are singletons.
    """
    arr = np.asarray(values, dtype=float)
    clu = np.asarray(clusters)
    groups = _group_by(arr, clu)
    g = len(groups)
    n = arr.size
    if g <= 1 or g == n:
        return 0.0
    grand_mean = arr.mean()
    ssb = sum(len(grp) * (grp.mean() - grand_mean) ** 2 for grp in groups)
    ssw = sum(((grp - grp.mean()) ** 2).sum() for grp in groups)
    msb = ssb / (g - 1)
    dof_w = n - g
    if dof_w <= 0:
        return 0.0
    msw = ssw / dof_w
    sizes = np.array([len(grp) for grp in groups], dtype=float)
    k0 = (n - (sizes**2).sum() / n) / (g - 1)
    if msw == 0 and msb == 0:
        return 0.0
    denom = msb + (k0 - 1) * msw
    if denom == 0:
        return 0.0
    icc = (msb - msw) / denom
    return float(np.clip(icc, -1.0, 1.0))


def design_effect(icc: float, avg_cluster_size: float) -> float:
    """Kish's design effect: 1 + (avg_cluster_size - 1) * ICC."""
    return 1.0 + (avg_cluster_size - 1.0) * icc


def cluster_robust_se(values: ArrayLike, clusters: ArrayLike) -> float:
    """Cluster-robust SE of the sample mean.

    Equivalent to fitting OLS of ``values`` on a constant with
    ``cov_type="cluster"`` in statsmodels (CR1 sandwich estimator with the
    default small-sample correction ``G/(G-1) * (N-1)/(N-K)``). See
    MacKinnon & White (1985) and Cameron, Gelbach & Miller (2011).
    """
    arr = np.asarray(values, dtype=float)
    clu = np.asarray(clusters)
    n = arr.size
    mean = arr.mean()
    resid = arr - mean
    groups = _group_by(resid, clu)
    g = len(groups)
    meat = sum(float(grp.sum()) ** 2 for grp in groups)
    if g <= 1:
        # Falls back to the (unbiased) heteroskedasticity-robust / CLT SE.
        return float(np.sqrt((resid**2).sum() / (n * (n - 1))))
    # Small-sample correction G/(G-1) * (N-1)/(N-K), with K=1 (the constant),
    # so (N-1)/(N-K) = 1 and only the cluster-count term survives.
    correction = g / (g - 1)
    variance = (meat / n**2) * correction
    return float(np.sqrt(max(variance, 0.0)))


def within_between_variance(
    values: ArrayLike, question_ids: ArrayLike
) -> tuple[float, float]:
    """Decompose variance across repeated samples per question.

    Returns ``(var_within, var_between)`` where ``var_within`` is the mean
    per-question sampling variance (decoding noise across repeated samples
    of the same question) and ``var_between`` is the variance of the
    per-question means (item difficulty). Uses the standard one-way
    random-effects moment estimator: ``var_between = max(0, MSB - MSW) /
    k0`` with the same unequal-group correction as ``intraclass_correlation``.
    """
    arr = np.asarray(values, dtype=float)
    qid = np.asarray(question_ids)
    groups = _group_by(arr, qid)
    q = len(groups)
    n = arr.size
    within_terms = [((grp - grp.mean()) ** 2).sum() for grp in groups if len(grp) > 1]
    within_dof = sum(len(grp) - 1 for grp in groups if len(grp) > 1)
    var_within = float(sum(within_terms) / within_dof) if within_dof > 0 else 0.0
    if q <= 1:
        return var_within, 0.0
    grand_mean = arr.mean()
    ssb = sum(len(grp) * (grp.mean() - grand_mean) ** 2 for grp in groups)
    msb = ssb / (q - 1)
    sizes = np.array([len(grp) for grp in groups], dtype=float)
    k0 = (n - (sizes**2).sum() / n) / (q - 1) if q > 1 else 1.0
    var_between = float(max(0.0, (msb - var_within) / k0)) if k0 > 0 else max(0.0, msb)
    return var_within, var_between
