"""Monte Carlo coverage tests: simulate known-truth data and check that the
nominal 95% CIs actually cover the true parameter about 95% of the time.

Trial counts are chosen so the binomial standard error of the estimated
coverage is small enough that a generous tolerance won't flake: with
N=4000 trials, SE(coverage) = sqrt(0.95*0.05/4000) ~= 0.0034, so a +-0.02
band is about 6 SEs -- it will not spuriously fail from run-to-run noise
while still catching a genuinely miscalibrated interval.
"""

from __future__ import annotations

import numpy as np

from errorbars.stats import (
    bootstrap_ci,
    cluster_robust_se,
    mean_ci_clt,
    wilson_ci,
    z_for_confidence,
)

N_TRIALS = 4000
TOLERANCE = 0.02


def test_clt_ci_coverage_normal_data() -> None:
    rng = np.random.default_rng(1000)
    true_mean = 3.0
    n = 40
    covered = 0
    for _ in range(N_TRIALS):
        x = rng.normal(true_mean, 1.5, size=n)
        est = mean_ci_clt(x, confidence=0.95)
        covered += est.ci_low <= true_mean <= est.ci_high
    coverage = covered / N_TRIALS
    assert abs(coverage - 0.95) < TOLERANCE, f"CLT coverage {coverage:.3f} off nominal 0.95"


def test_wilson_ci_coverage_binomial_moderate_p() -> None:
    rng = np.random.default_rng(1001)
    true_p = 0.5
    n = 40
    covered = 0
    for _ in range(N_TRIALS):
        k = int(rng.binomial(n, true_p))
        est = wilson_ci(k, n, confidence=0.95)
        covered += est.ci_low <= true_p <= est.ci_high
    coverage = covered / N_TRIALS
    assert abs(coverage - 0.95) < TOLERANCE, f"Wilson coverage {coverage:.3f} off nominal 0.95"


def test_wilson_ci_coverage_beats_wald_near_extreme_p() -> None:
    # At p=0.05, n=30 the Wald/CLT interval badly under-covers; Wilson should
    # stay much closer to nominal. This demonstrates *why* errorbars defaults
    # to Wilson for small-n binary scores.
    rng = np.random.default_rng(1002)
    true_p = 0.05
    n = 30
    wilson_covered = 0
    wald_covered = 0
    trials = N_TRIALS
    z = z_for_confidence(0.95)
    for _ in range(trials):
        k = int(rng.binomial(n, true_p))
        w = wilson_ci(k, n, confidence=0.95)
        wilson_covered += w.ci_low <= true_p <= w.ci_high
        p_hat = k / n
        se = np.sqrt(p_hat * (1 - p_hat) / n) if 0 < p_hat < 1 else 0.0
        wald_lo, wald_hi = p_hat - z * se, p_hat + z * se
        wald_covered += wald_lo <= true_p <= wald_hi
    wilson_coverage = wilson_covered / trials
    wald_coverage = wald_covered / trials
    assert wilson_coverage > wald_coverage
    assert abs(wilson_coverage - 0.95) < 0.03


def test_bootstrap_ci_coverage_normal_data() -> None:
    rng = np.random.default_rng(1003)
    true_mean = -1.0
    n = 50
    covered = 0
    trials = 800  # bootstrap is slow; fewer trials, wider tolerance
    for i in range(trials):
        x = rng.normal(true_mean, 2.0, size=n)
        est = bootstrap_ci(x, confidence=0.95, n_boot=800, seed=i)
        covered += est.ci_low <= true_mean <= est.ci_high
    coverage = covered / trials
    assert abs(coverage - 0.95) < 0.045, f"bootstrap coverage {coverage:.3f} off nominal 0.95"


def test_cluster_robust_ci_coverage_with_clustered_data() -> None:
    # Ground truth: overall mean is 0. Data has a shared cluster effect, so
    # the naive (non-clustered) SE would under-cover; the cluster-robust SE
    # should cover close to nominal.
    rng = np.random.default_rng(1004)
    true_mean = 0.0
    n_clusters, size = 12, 6
    trials = N_TRIALS
    covered = 0
    z = z_for_confidence(0.95)
    for _ in range(trials):
        cluster_effect = rng.normal(0, 1.0, size=n_clusters)
        clusters = np.repeat(np.arange(n_clusters), size)
        noise = rng.normal(0, 0.5, size=n_clusters * size)
        values = np.repeat(cluster_effect, size) + noise
        mean = values.mean()
        se = cluster_robust_se(values, clusters)
        lo, hi = mean - z * se, mean + z * se
        covered += lo <= true_mean <= hi
    coverage = covered / trials
    # With only 12 clusters the small-sample correction is imperfect (a
    # known property of cluster-robust SEs -- see docs/formulas.md), so we
    # use a looser band than the single-level CLT test above.
    assert abs(coverage - 0.95) < 0.05, f"clustered coverage {coverage:.3f} off nominal 0.95"
