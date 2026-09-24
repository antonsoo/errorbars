"""Exact-agreement tests against statsmodels/scipy oracles.

statsmodels and scipy are test-only dependencies (see pyproject.toml
dev group); errorbars itself never imports them at runtime.
"""

from __future__ import annotations

import numpy as np
import pytest
import statsmodels.api as sm
from scipy import stats as sp_stats
from statsmodels.stats.proportion import proportion_confint

from errorbars.stats import (
    cluster_robust_se,
    design_effect,
    intraclass_correlation,
    mean_ci_clt,
    wilson_ci,
    z_for_confidence,
)


def _make_clustered(seed: int, n_clusters: int = 20, min_size: int = 2, max_size: int = 9):
    rng = np.random.default_rng(seed)
    sizes = rng.integers(min_size, max_size, size=n_clusters)
    cluster_effect = rng.normal(0, 1.3, size=n_clusters)
    clusters, values = [], []
    for c, s in enumerate(sizes):
        clusters += [c] * s
        values += list(cluster_effect[c] + rng.normal(0, 1.0, size=s))
    return np.array(values), np.array(clusters)


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 123])
def test_cluster_robust_se_matches_statsmodels_ols(seed: int) -> None:
    values, clusters = _make_clustered(seed)
    ours = cluster_robust_se(values, clusters)

    X = np.ones((len(values), 1))
    model = sm.OLS(values, X).fit(cov_type="cluster", cov_kwds={"groups": clusters})
    theirs = float(model.bse[0])

    assert ours == pytest.approx(theirs, rel=1e-9)


@pytest.mark.parametrize("seed", [0, 1, 7])
def test_cluster_robust_se_unbalanced_clusters(seed: int) -> None:
    values, clusters = _make_clustered(seed, n_clusters=8, min_size=1, max_size=15)
    ours = cluster_robust_se(values, clusters)
    X = np.ones((len(values), 1))
    model = sm.OLS(values, X).fit(cov_type="cluster", cov_kwds={"groups": clusters})
    assert ours == pytest.approx(float(model.bse[0]), rel=1e-9)


def test_z_for_confidence_matches_scipy() -> None:
    for conf in (0.80, 0.90, 0.95, 0.99):
        ours = z_for_confidence(conf)
        theirs = sp_stats.norm.ppf(0.5 + conf / 2)
        assert ours == pytest.approx(theirs, rel=1e-12)


@pytest.mark.parametrize("k,n", [(3, 10), (45, 100), (0, 20), (20, 20), (1, 1000)])
def test_wilson_ci_matches_statsmodels(k: int, n: int) -> None:
    ours = wilson_ci(k, n, confidence=0.95)
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    assert ours.ci_low == pytest.approx(lo, abs=1e-9)
    assert ours.ci_high == pytest.approx(hi, abs=1e-9)


def test_mean_ci_clt_matches_manual_normal_formula() -> None:
    rng = np.random.default_rng(3)
    x = rng.normal(5, 2, size=50)
    est = mean_ci_clt(x, confidence=0.95)
    mean = x.mean()
    se = x.std(ddof=1) / np.sqrt(len(x))
    z = sp_stats.norm.ppf(0.975)
    assert est.mean == pytest.approx(mean)
    assert est.se == pytest.approx(se)
    assert est.ci_low == pytest.approx(mean - z * se)
    assert est.ci_high == pytest.approx(mean + z * se)


def test_intraclass_correlation_zero_for_single_cluster() -> None:
    values = np.arange(10.0)
    clusters = np.zeros(10)
    assert intraclass_correlation(values, clusters) == 0.0


def test_intraclass_correlation_high_when_within_cluster_identical() -> None:
    # Clusters are internally constant but differ across clusters: ICC -> 1.
    values = np.repeat([1.0, 5.0, 9.0, 20.0], 5)
    clusters = np.repeat([0, 1, 2, 3], 5)
    icc = intraclass_correlation(values, clusters)
    assert icc == pytest.approx(1.0, abs=1e-9)


def test_design_effect_formula() -> None:
    assert design_effect(icc=0.0, avg_cluster_size=5) == pytest.approx(1.0)
    assert design_effect(icc=1.0, avg_cluster_size=5) == pytest.approx(5.0)
    assert design_effect(icc=0.5, avg_cluster_size=3) == pytest.approx(2.0)
