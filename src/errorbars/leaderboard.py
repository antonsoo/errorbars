"""Multi-model leaderboards with paired pairwise tests and Holm correction."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from errorbars.compare import PairedComparison, paired_compare
from errorbars.io import EvalData
from errorbars.stats import MeanEstimate, is_binary, mean_ci_clt, wilson_ci

__all__ = ["LeaderboardEntry", "PairwiseResult", "Leaderboard", "build_leaderboard", "holm_correction"]


def holm_correction(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values (Holm, 1979).

    Controls the family-wise error rate without assuming independence,
    less conservative than plain Bonferroni. Matches
    ``statsmodels.stats.multitest.multipletests(p, method="holm")``.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, i in enumerate(order):
        raw = (m - rank) * p_values[i]
        running_max = max(running_max, raw)
        adjusted[i] = min(1.0, running_max)
    return adjusted


@dataclass(frozen=True)
class LeaderboardEntry:
    model: str
    mean: float
    se: float
    ci_low: float
    ci_high: float
    n: int
    method: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "mean": self.mean,
            "se": self.se,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "n": self.n,
            "method": self.method,
        }


@dataclass(frozen=True)
class PairwiseResult:
    model_a: str
    model_b: str
    comparison: PairedComparison
    p_holm: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "mean_diff": self.comparison.mean_diff,
            "p_value": self.comparison.p_value,
            "p_holm": self.p_holm,
        }


@dataclass(frozen=True)
class Leaderboard:
    entries: list[LeaderboardEntry]  # sorted by mean, descending
    pairwise: list[PairwiseResult]
    groups: list[list[str]]  # each group: models not significantly different (Holm alpha)
    alpha: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.as_dict() for e in self.entries],
            "pairwise": [p.as_dict() for p in self.pairwise],
            "groups": self.groups,
            "alpha": self.alpha,
        }


def _maximal_cliques(nodes: list[str], edges: set[frozenset[str]]) -> list[list[str]]:
    """Bron-Kerbosch without pivoting; fine for leaderboard-sized graphs."""

    def neighbors(v: str) -> set[str]:
        return {u for u in nodes if u != v and frozenset((u, v)) in edges}

    adj = {v: neighbors(v) for v in nodes}
    cliques: list[set[str]] = []

    def bron_kerbosch(r: set[str], p: set[str], x: set[str]) -> None:
        if not p and not x:
            cliques.append(r)
            return
        for v in list(p):
            bron_kerbosch(r | {v}, p & adj[v], x & adj[v])
            p = p - {v}
            x = x | {v}

    bron_kerbosch(set(), set(nodes), set())
    # sort each clique by the leaderboard's original node order for stable display
    order = {v: i for i, v in enumerate(nodes)}
    cliques_sorted = [sorted(c, key=lambda v: order[v]) for c in cliques]
    cliques_sorted.sort(key=lambda c: (order[c[0]], -len(c)))
    return cliques_sorted


def build_leaderboard(
    data: EvalData,
    confidence: float = 0.95,
    alpha: float = 0.05,
    use_wilson_below_n: int = 30,
) -> Leaderboard:
    """Build a leaderboard: per-model CIs, Holm-corrected pairwise tests, groups.

    ``use_wilson_below_n``: for binary scores with fewer than this many
    questions, per-model CIs use the Wilson interval instead of the CLT
    interval (see ``errorbars.stats.wilson_ci``).
    """
    models = data.models()
    if len(models) < 2:
        raise ValueError("leaderboard needs at least 2 models")

    per_model_scores: dict[str, list[float]] = {m: data.filter_model(m).score for m in models}

    entries: list[LeaderboardEntry] = []
    for m in models:
        scores = per_model_scores[m]
        est = _summarize_mean(scores, confidence, use_wilson_below_n)
        entries.append(LeaderboardEntry(m, est.mean, est.se, est.ci_low, est.ci_high, est.n, est.method))
    entries.sort(key=lambda e: e.mean, reverse=True)
    order = [e.model for e in entries]

    # Align questions for paired tests: use the intersection of question_ids
    # common to both models, sorted for determinism.
    qmap = {m: data.filter_model(m).scores_by_question() for m in models}
    cluster_of_q = data.cluster_by_question()

    pairwise: list[PairwiseResult] = []
    raw_p: list[float] = []
    pair_keys: list[tuple[str, str]] = []
    for a, b in combinations(order, 2):
        common = sorted(set(qmap[a]) & set(qmap[b]))
        if len(common) < 2:
            continue
        sa = [qmap[a][q] for q in common]
        sb = [qmap[b][q] for q in common]
        clusters = [cluster_of_q[q] for q in common] if cluster_of_q else None
        has_real_clusters = clusters is not None and len(set(clusters)) < len(clusters)
        comp = paired_compare(sa, sb, clusters=clusters if has_real_clusters else None, confidence=confidence)
        pair_keys.append((a, b))
        # Prefer the cluster-robust p-value when clusters are present: it is
        # the honest one when questions are correlated within a cluster.
        raw_p.append(comp.p_value_clustered if comp.p_value_clustered is not None else comp.p_value)
        pairwise.append(PairwiseResult(a, b, comp, p_holm=raw_p[-1]))  # placeholder, fixed below

    adjusted = holm_correction(raw_p) if raw_p else []
    pairwise = [
        PairwiseResult(a, b, pr.comparison, p_holm)
        for (a, b), pr, p_holm in zip(pair_keys, pairwise, adjusted, strict=True)
    ]

    edges = {frozenset((pr.model_a, pr.model_b)) for pr in pairwise if pr.p_holm >= alpha}
    groups = _maximal_cliques(order, edges)

    return Leaderboard(entries=entries, pairwise=pairwise, groups=groups, alpha=alpha)


def _summarize_mean(scores: list[float], confidence: float, use_wilson_below_n: int) -> MeanEstimate:
    n = len(scores)
    if is_binary(scores) and n < use_wilson_below_n:
        successes = int(round(sum(scores)))
        return wilson_ci(successes, n, confidence)
    return mean_ci_clt(scores, confidence)
