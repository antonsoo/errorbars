"""Clustered inference when the clusters are few or very unequal in size.

The classic CR1 sandwich on t(G - 1) is what most packages report. It is fine
for many clusters of similar size and wrong for a benchmark like SWE-bench
Verified, where 12 repositories hold 500 tasks and one of them holds 231.
"""

from __future__ import annotations

import itertools
import math
import random
import time

import numpy as np
import pytest
from oracles import cr2_mean_oracle
from scipy import stats as sp_stats

from errorbars.compare import paired_compare
from errorbars.leaderboard import _maximal_cliques
from errorbars.stats import cluster_degrees_of_freedom, cluster_robust_se

# Tasks per repository in SWE-bench Verified (django, sympy, sphinx, ...).
SWE_BENCH_VERIFIED_REPOS = [231, 75, 44, 34, 32, 22, 22, 19, 10, 8, 2, 1]


def _labels(sizes: list[int]) -> np.ndarray:
    return np.repeat(np.arange(len(sizes)), sizes)


@pytest.mark.parametrize("seed", range(8))
def test_cr2_and_its_degrees_of_freedom_match_the_matrix_definition(seed: int) -> None:
    rng = np.random.default_rng(seed)
    sizes = [int(s) for s in rng.integers(1, 30, size=int(rng.integers(2, 12)))]
    clusters = _labels(sizes)
    values = rng.normal(0.4, 1.0, size=clusters.size) + rng.normal(0, 0.5, size=len(sizes))[clusters]
    se, dof = cr2_mean_oracle(values, clusters.tolist())
    assert cluster_robust_se(values, clusters) == pytest.approx(se, rel=1e-9)
    assert cluster_degrees_of_freedom(clusters) == pytest.approx(dof, rel=1e-9)


def test_swe_bench_verified_has_about_three_effective_degrees_of_freedom() -> None:
    clusters = _labels(SWE_BENCH_VERIFIED_REPOS)
    _, dof = cr2_mean_oracle(np.zeros(clusters.size), clusters.tolist())
    assert cluster_degrees_of_freedom(clusters) == pytest.approx(dof, rel=1e-9)
    assert cluster_degrees_of_freedom(clusters) == pytest.approx(3.331, abs=5e-4)


def test_equal_clusters_reduce_to_the_classic_estimator() -> None:
    rng = np.random.default_rng(11)
    clusters = _labels([7] * 15)
    values = rng.normal(size=clusters.size)
    classic = cluster_robust_se(values, clusters, kind="CR1")
    assert cluster_robust_se(values, clusters) == pytest.approx(classic)
    assert cluster_degrees_of_freedom(clusters) == pytest.approx(14.0)


def test_singleton_clusters_reduce_to_the_ordinary_standard_error() -> None:
    rng = np.random.default_rng(12)
    values = rng.normal(size=40)
    clusters = np.arange(40)
    assert cluster_robust_se(values, clusters) == pytest.approx(values.std(ddof=1) / math.sqrt(40))
    assert cluster_degrees_of_freedom(clusters) == pytest.approx(39.0)


def test_degrees_of_freedom_do_not_depend_on_labels_or_order() -> None:
    clusters = ["b", "a", "a", "c", "a", "b", "c", "c", "c"]
    shuffled = ["z", "z", "z", "z", 3, 3, 3, "q", "q"]
    assert cluster_degrees_of_freedom(clusters) == pytest.approx(cluster_degrees_of_freedom(shuffled))


@pytest.mark.parametrize("clusters", [["a", "a", "a"], [], [1]])
def test_degrees_of_freedom_need_two_clusters(clusters: list[object]) -> None:
    with pytest.raises(ValueError):
        cluster_degrees_of_freedom(clusters)


def test_unknown_estimator_is_refused() -> None:
    with pytest.raises(ValueError, match="CR1.*CR2"):
        cluster_robust_se([0.1, 0.4, 0.2, 0.9], [0, 0, 1, 1], kind="HC3")


def _rejection_rates(repo_effect_sd: float, reps: int, seed: int) -> tuple[float, float]:
    """Share of true nulls rejected at 5% by (CR1 on t(G-1), CR2 on Satterthwaite t).

    Paired differences in {-1, 0, 1} on SWE-bench Verified's repository sizes.
    Each repository has its own true advantage, drawn with mean zero, so the
    null (no advantage on average over repositories) holds.
    """
    sizes = np.array(SWE_BENCH_VERIFIED_REPOS)
    n, g = int(sizes.sum()), sizes.size
    lab = _labels(SWE_BENCH_VERIFIED_REPOS)
    share = sizes / n
    dof = cluster_degrees_of_freedom(lab)
    crit_cr1 = sp_stats.t.ppf(0.975, g - 1)
    crit_cr2 = sp_stats.t.ppf(0.975, dof)
    rng = np.random.default_rng(seed)
    rejected_cr1 = rejected_cr2 = 0
    for _ in range(reps):
        advantage = rng.normal(0.0, repo_effect_sd, g)
        p_win = np.clip(0.07 + advantage / 2, 0, 0.5)[lab]
        p_loss = np.clip(0.07 - advantage / 2, 0, 0.5)[lab]
        u = rng.random(n)
        d = np.where(u < p_win, 1.0, np.where(u < p_win + p_loss, -1.0, 0.0))
        sums = np.bincount(lab, weights=d - d.mean(), minlength=g)
        cr1 = math.sqrt((sums**2).sum() * g / (g - 1)) / n
        cr2 = math.sqrt((sums**2 / (1 - share)).sum()) / n
        rejected_cr1 += abs(d.mean()) > crit_cr1 * cr1
        rejected_cr2 += abs(d.mean()) > crit_cr2 * cr2
    return rejected_cr1 / reps, rejected_cr2 / reps


@pytest.mark.parametrize("repo_effect_sd", [0.0, 0.04])
def test_the_classic_test_over_rejects_on_swe_bench_sizes_and_the_default_does_not(
    repo_effect_sd: float,
) -> None:
    cr1, cr2 = _rejection_rates(repo_effect_sd, reps=4000, seed=5)
    # Binomial noise at 4,000 replications is about 0.35 points (one sd) around 5%.
    assert cr1 > 0.075, f"CR1/t(G-1) rejected {cr1:.3f}: expected clear over-rejection"
    assert cr2 < 0.065, f"CR2/Satterthwaite rejected {cr2:.3f}: expected at most nominal"


def test_the_simulation_statistic_is_the_library_statistic() -> None:
    # Guards the vectorised arithmetic above against drifting from the library.
    rng = np.random.default_rng(2)
    lab = _labels(SWE_BENCH_VERIFIED_REPOS)
    d = rng.choice([-1.0, 0.0, 1.0], size=lab.size, p=[0.07, 0.86, 0.07])
    sums = np.bincount(lab, weights=d - d.mean())
    share = np.array(SWE_BENCH_VERIFIED_REPOS) / lab.size
    assert cluster_robust_se(d, lab) == pytest.approx(math.sqrt((sums**2 / (1 - share)).sum()) / lab.size)
    assert cluster_robust_se(d, lab, kind="CR1") == pytest.approx(
        math.sqrt((sums**2).sum() * 12 / 11) / lab.size
    )


def test_paired_comparison_reports_and_explains_few_effective_clusters() -> None:
    rng = np.random.default_rng(3)
    lab = _labels(SWE_BENCH_VERIFIED_REPOS)
    a = (rng.random(lab.size) < 0.78).astype(float)
    b = (rng.random(lab.size) < 0.74).astype(float)
    comp = paired_compare(a, b, clusters=lab)
    assert comp.n_clusters == 12
    assert comp.dof_clustered == pytest.approx(3.331, abs=5e-4)
    assert comp.se_clustered is not None and comp.p_value_clustered is not None
    t_stat = comp.mean_diff / comp.se_clustered
    expected_p = 2 * sp_stats.t.sf(abs(t_stat), comp.dof_clustered)
    assert comp.p_value_clustered == pytest.approx(expected_p, rel=1e-7)
    crit = sp_stats.t.ppf(0.975, comp.dof_clustered)
    assert comp.ci_high_clustered == pytest.approx(comp.mean_diff + crit * comp.se_clustered, rel=1e-7)
    assert comp.as_dict()["dof_clustered"] == comp.dof_clustered
    note = next(w for w in comp.warnings if "effective degrees of freedom" in w)
    assert "3.3" in note and "12 clusters" in note and "46%" in note


def test_many_equal_clusters_raise_no_few_cluster_note() -> None:
    rng = np.random.default_rng(4)
    lab = _labels([5] * 40)
    comp = paired_compare(rng.normal(size=200), rng.normal(size=200), clusters=lab)
    assert comp.dof_clustered == pytest.approx(39.0)
    assert not any("effective degrees of freedom" in w for w in comp.warnings)


def _brute_force_maximal_cliques(nodes: list[str], edges: set[frozenset[str]]) -> list[list[str]]:
    cliques = [
        set(c)
        for k in range(1, len(nodes) + 1)
        for c in itertools.combinations(nodes, k)
        if all(frozenset(pair) in edges for pair in itertools.combinations(c, 2))
    ]
    return sorted(sorted(c) for c in cliques if not any(c < other for other in cliques))


def test_indistinguishable_groups_match_brute_force_on_random_graphs() -> None:
    rnd = random.Random(3)
    for _ in range(200):
        nodes = [f"m{i}" for i in range(rnd.randint(1, 9))]
        density = rnd.choice([0.2, 0.5, 0.9])
        edges = {frozenset(p) for p in itertools.combinations(nodes, 2) if rnd.random() < density}
        assert sorted(sorted(c) for c in _maximal_cliques(nodes, edges)) == _brute_force_maximal_cliques(
            nodes, edges
        )


def test_a_large_tied_leaderboard_is_grouped_quickly() -> None:
    # 28 near-tied real submissions took 66 s before pivoting; 47 did not finish.
    nodes = [f"m{i:03d}" for i in range(300)]
    edges = {frozenset((a, b)) for i, a in enumerate(nodes) for b in nodes[i + 1 : i + 80]}
    started = time.perf_counter()
    cliques = _maximal_cliques(nodes, edges)
    assert time.perf_counter() - started < 5.0
    assert len(cliques) == 221 and all(len(c) == 80 for c in cliques)
