"""Paired comparison and McNemar tests, cross-checked against scipy/statsmodels."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats as sp_stats
from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar

from errorbars.compare import mcnemar_exact, paired_compare


@pytest.mark.parametrize(("seed", "n"), [(0, 80), (1, 80), (5, 80), (11, 80), (2, 8), (3, 15)])
def test_paired_ttest_matches_scipy(seed: int, n: int) -> None:
    rng = np.random.default_rng(seed)
    a = rng.normal(0.7, 0.2, size=n)
    b = a + rng.normal(0.05, 0.15, size=n)  # correlated with a, shifted
    comp = paired_compare(a, b)

    diff = a - b
    mean = diff.mean()
    se = diff.std(ddof=1) / np.sqrt(n)
    assert comp.mean_diff == pytest.approx(mean)
    assert comp.se_paired == pytest.approx(se)

    t_scipy, p_scipy = sp_stats.ttest_rel(a, b)
    # Student t with n - 1 degrees of freedom, like ttest_rel, at any n.
    assert comp.p_value == pytest.approx(p_scipy, rel=1e-7)
    t_crit = sp_stats.t.ppf(0.975, n - 1)
    assert comp.ci_low == pytest.approx(mean - t_crit * se, rel=1e-7)
    assert comp.ci_high == pytest.approx(mean + t_crit * se, rel=1e-7)

    r_scipy = sp_stats.pearsonr(a, b).statistic
    assert comp.correlation == pytest.approx(r_scipy, abs=1e-9)


def test_paired_compare_variance_reduction_positive_for_correlated_scores() -> None:
    rng = np.random.default_rng(9)
    n = 200
    shared = rng.normal(0, 1, size=n)
    a = shared + rng.normal(0, 0.3, size=n)
    b = shared + rng.normal(0, 0.3, size=n)
    comp = paired_compare(a, b)
    assert comp.correlation > 0.8
    assert comp.variance_reduction > 0.7
    assert comp.se_paired < comp.se_unpaired


@pytest.mark.parametrize(
    "a,b",
    [
        ([1, 1, 0, 0, 1, 0, 1, 0, 1, 1], [1, 0, 0, 1, 1, 0, 0, 0, 1, 1]),
        ([1] * 5 + [0] * 5, [0] * 5 + [1] * 5),
        ([1, 0, 1, 0], [1, 0, 1, 0]),
    ],
)
def test_mcnemar_exact_matches_statsmodels(a: list[int], b: list[int]) -> None:
    ours = mcnemar_exact(a, b)
    a_arr, b_arr = np.array(a), np.array(b)
    n01 = int(np.sum((a_arr == 0) & (b_arr == 1)))
    n10 = int(np.sum((a_arr == 1) & (b_arr == 0)))
    n11 = int(np.sum((a_arr == 1) & (b_arr == 1)))
    n00 = int(np.sum((a_arr == 0) & (b_arr == 0)))
    table = [[n11, n10], [n01, n00]]
    theirs = sm_mcnemar(table, exact=True)
    assert ours.n01 == n01
    assert ours.n10 == n10
    assert ours.p_value == pytest.approx(theirs.pvalue, abs=1e-9)


def test_mcnemar_result_flows_through_paired_compare_for_binary_scores() -> None:
    rng = np.random.default_rng(2)
    a = (rng.uniform(size=60) < 0.6).astype(float)
    b = (rng.uniform(size=60) < 0.5).astype(float)
    comp = paired_compare(a, b)
    assert comp.mcnemar is not None
    assert comp.mcnemar.n01 >= 0 and comp.mcnemar.n10 >= 0


def test_paired_compare_with_clusters_matches_cluster_robust_se() -> None:
    from errorbars.stats import cluster_robust_se

    rng = np.random.default_rng(4)
    n_clusters, size = 15, 6
    clusters = np.repeat(np.arange(n_clusters), size)
    a = rng.normal(0.6, 0.2, size=n_clusters * size)
    b = rng.normal(0.55, 0.2, size=n_clusters * size)
    comp = paired_compare(a, b, clusters=clusters)
    expected_se = cluster_robust_se(a - b, clusters)
    assert comp.se_clustered == pytest.approx(expected_se)


def test_clustered_comparison_uses_t_with_clusters_minus_one_dof() -> None:
    rng = np.random.default_rng(4)
    clusters = np.repeat(np.arange(12), 5)  # 12 clusters of 5 questions
    shared = np.repeat(rng.normal(0, 0.3, size=12), 5)
    a = 0.6 + shared + rng.normal(0, 0.2, size=60)
    b = a - 0.08 + rng.normal(0, 0.2, size=60)
    comp = paired_compare(a, b, clusters=clusters)
    assert comp.se_clustered is not None and comp.p_value_clustered is not None
    t_stat = comp.mean_diff / comp.se_clustered
    assert comp.p_value_clustered == pytest.approx(2 * sp_stats.t.sf(abs(t_stat), 11), rel=1e-7)
    t_crit = sp_stats.t.ppf(0.975, 11)
    assert comp.ci_high_clustered == pytest.approx(comp.mean_diff + t_crit * comp.se_clustered, rel=1e-7)
