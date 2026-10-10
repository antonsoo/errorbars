"""Multi-model leaderboards with paired pairwise tests and Holm correction."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Any

from errorbars.compare import FEW_CLUSTER_DOF, PairedComparison, PairedTest, paired_compare, select_inference
from errorbars.io import EvalData
from errorbars.stats import (
    MeanEstimate,
    cluster_degrees_of_freedom,
    cluster_robust_se,
    is_binary,
    mean_ci_clt,
    prefer_wilson,
    t_for_confidence,
    wilson_ci,
)

__all__ = [
    "LeaderboardEntry", "PairwiseResult", "UntestedPair", "Leaderboard",
    "build_leaderboard", "holm_correction", "rank_ranges",
]


def rank_ranges(ranks: list[int]) -> str:
    """Compact exact ranks, preserving holes; '-' means no other ranks."""
    ordered = sorted(set(ranks))
    ranges: list[str] = []
    previous = start = 0
    for rank in ordered:
        if not ranges or rank != previous + 1:
            ranges.append(str(rank))
            start = rank
        else:
            ranges[-1] = f"{start}-{rank}"
        previous = rank
    return ", ".join(ranges) or "-"


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
    n_observations: int = 0
    confidence: float = 0.95
    n_clusters: int | None = None
    dof_clustered: float | None = None
    unclustered: MeanEstimate | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.n_observations == 0:
            object.__setattr__(self, "n_observations", self.n)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "mean": self.mean,
            "se": self.se,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "n": self.n,
            "method": self.method,
            "n_observations": self.n_observations,
            "analysis_unit": "question",
            "confidence": self.confidence,
            "n_clusters": self.n_clusters,
            "dof_clustered": self.dof_clustered,
            "unclustered": self.unclustered.as_dict() if self.unclustered else None,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class PairwiseResult:
    model_a: str
    model_b: str
    comparison: PairedComparison
    p_holm: float
    test: PairedTest = "paired_t"

    @property
    def p_value_used(self) -> float:
        """Raw p-value selected before the board-wide Holm correction."""
        if self.test == "clustered_t":
            assert self.comparison.p_value_clustered is not None
            return self.comparison.p_value_clustered
        if self.test == "mcnemar_exact":
            assert self.comparison.mcnemar is not None
            return self.comparison.mcnemar.p_value
        return self.comparison.p_value

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "mean_diff": self.comparison.mean_diff,
            "p_value": self.comparison.p_value,
            "p_value_clustered": self.comparison.p_value_clustered,
            "mcnemar": self.comparison.mcnemar.as_dict() if self.comparison.mcnemar else None,
            "test": self.test,
            "p_value_used": self.p_value_used,
            "p_holm": self.p_holm,
            "n_shared": self.comparison.n,
            "warnings": self.comparison.warnings,
        }


@dataclass(frozen=True)
class UntestedPair:
    model_a: str
    model_b: str
    n_shared: int
    reason: str = "fewer_than_two_shared_questions"


@dataclass(frozen=True)
class Leaderboard:
    entries: list[LeaderboardEntry]  # sorted by mean, descending
    pairwise: list[PairwiseResult]
    groups: list[list[str]]  # each group: models not significantly different (Holm alpha)
    alpha: float
    untested_pairs: list[UntestedPair] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def rank_comparisons(self) -> dict[str, dict[str, list[int]]]:
        """Exact other-model ranks by decision; non-significance is not transitive.

        Self is never a comparison. Missing pairs are untested, not significant
        or non-significant. Use these sets rather than a min-max rank envelope.
        """
        ranks = {entry.model: rank for rank, entry in enumerate(self.entries, 1)}
        result: dict[str, dict[str, list[int]]] = {
            model: {"non_significant": [], "significant": [], "untested": []} for model in ranks
        }
        decisions = {
            frozenset((pair.model_a, pair.model_b)):
            "significant" if pair.p_holm < self.alpha else "non_significant"
            for pair in self.pairwise
        }
        for a, b in combinations(ranks, 2):
            decision = decisions.get(frozenset((a, b)), "untested")
            result[a][decision].append(ranks[b])
            result[b][decision].append(ranks[a])
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.as_dict() for e in self.entries],
            "pairwise": [p.as_dict() for p in self.pairwise],
            "groups": self.groups,
            "alpha": self.alpha,
            "rank_comparisons": self.rank_comparisons(),
            "untested_pairs": [asdict(pair) for pair in self.untested_pairs],
            "warnings": self.warnings,
        }


def _maximal_cliques(nodes: list[str], edges: set[frozenset[str]]) -> list[list[str]]:
    """Bron-Kerbosch with pivoting (Tomita, Tanaka & Takahashi 2006).

    A leaderboard whose top entries are tied is close to one big clique, the
    worst case for the unpivoted algorithm: it took a minute for 28 real
    SWE-bench Verified submissions and did not finish for 47. Branching only
    on candidates outside the pivot's neighbourhood visits each maximal clique
    about once. Iterative, so a large tied group cannot exhaust the stack.
    """
    order = {v: i for i, v in enumerate(nodes)}
    adj: dict[str, set[str]] = {v: set() for v in nodes}
    for edge in edges:
        u, v = tuple(edge)
        adj[u].add(v)
        adj[v].add(u)

    cliques: list[set[str]] = []
    stack: list[tuple[set[str], set[str], set[str]]] = [(set(), set(nodes), set())]
    while stack:
        r, p, x = stack.pop()
        if not p:
            if not x:
                cliques.append(r)
            continue
        pivot = max(p | x, key=lambda u: (len(p & adj[u]), -order[u]))
        for v in sorted(p - adj[pivot], key=order.__getitem__):
            stack.append((r | {v}, p & adj[v], x & adj[v]))
            p = p - {v}
            x = x | {v}

    # sort each clique by the leaderboard's original node order for stable display
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
    questions, or fewer than 10 successes or failures, per-model CIs use the
    Wilson interval instead of the CLT interval (see
    ``errorbars.stats.prefer_wilson``). With multi-question clusters, the
    displayed interval instead uses CR2 and Student t with effective degrees
    of freedom; the unclustered estimate is retained as a diagnostic. Means
    always weight questions equally, even with unequal numbers of generations.

    Pairwise grouping uses clustered t when multiple shared questions belong to a
    cluster, exact McNemar for one binary observation per shared question
    without such clusters, and paired t for continuous or repeated-generation
    question means. The method is selected from the data structure, never
    from whichever test gives the smaller p-value. Holm is applied once to
    all selected raw p-values, including boards with mixed score types.
    """
    data.validate()
    models = data.models()
    if len(models) < 2:
        raise ValueError("leaderboard needs at least 2 models")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    qmap = {m: data.filter_model(m).scores_by_question() for m in models}
    counts = {m: Counter(data.filter_model(m).question_id) for m in models}
    n_observations = {m: len(data.filter_model(m)) for m in models}
    cluster_of_q = data.cluster_by_question()

    entries: list[LeaderboardEntry] = []
    for m in models:
        scores = list(qmap[m].values())
        repeated = n_observations[m] > len(scores)
        if repeated and len(scores) < 2:
            raise ValueError(
                f"model {m!r}: need at least 2 distinct questions for repeated-generation inference"
            )
        est = _summarize_mean(scores, confidence, None if repeated else use_wilson_below_n)
        unclustered = None
        n_clusters, dof = None, None
        notes = []
        clusters = [cluster_of_q[q] for q in qmap[m]] if cluster_of_q else None
        if clusters is not None and len(set(clusters)) < len(clusters):
            n_clusters = len(set(clusters))
            if n_clusters < 2:
                raise ValueError(f"model {m!r}: need at least 2 independent clusters for an interval")
            unclustered = est
            se = cluster_robust_se(scores, clusters)
            dof = cluster_degrees_of_freedom(clusters)
            half_width = t_for_confidence(confidence, dof) * se
            est = MeanEstimate(
                est.mean, se, est.mean - half_width, est.mean + half_width, confidence, "clustered_cr2", est.n
            )
            if dof < FEW_CLUSTER_DOF:
                notes.append(
                    f"The interval uses {n_clusters} clusters and {dof:.1f} effective "
                    "degrees of freedom; few independent clusters limit precision."
                )
            if se == 0:
                notes.append(
                    "Cluster residual sums have zero estimated variance; "
                    "a point interval does not establish population certainty."
                )
        entries.append(
            LeaderboardEntry(
                m,
                est.mean,
                est.se,
                est.ci_low,
                est.ci_high,
                est.n,
                est.method,
                n_observations[m],
                confidence=confidence,
                n_clusters=n_clusters,
                dof_clustered=dof,
                unclustered=unclustered,
                warnings=notes,
            )
        )
    entries.sort(key=lambda e: e.mean, reverse=True)
    order = [e.model for e in entries]

    # Align questions for paired tests: use the intersection of question_ids
    # common to both models, sorted for determinism.
    pairwise: list[PairwiseResult] = []
    untested_pairs: list[UntestedPair] = []
    raw_p: list[float] = []
    for a, b in combinations(order, 2):
        conflicts = data.pairing_conflicts(a, b)
        if conflicts:
            raise ValueError(
                f"{a!r} vs {b!r}: conflicting question content for {len(conflicts)} shared ids "
                f"(including {conflicts[0]!r}); inspect the source records before pairing"
            )
        common = sorted(set(qmap[a]) & set(qmap[b]))
        if len(common) < 2:
            untested_pairs.append(UntestedPair(a, b, len(common)))
            continue
        sa = [qmap[a][q] for q in common]
        sb = [qmap[b][q] for q in common]
        clusters = [cluster_of_q[q] for q in common] if cluster_of_q else None
        has_real_clusters = clusters is not None and len(set(clusters)) < len(clusters)
        comp = paired_compare(sa, sb, clusters=clusters if has_real_clusters else None, confidence=confidence)
        inference = select_inference(
            comp, single_observation_per_question=all(counts[m][q] == 1 for m in (a, b) for q in common),
        )
        result = PairwiseResult(a, b, comp, p_holm=1.0, test=inference.test)
        raw_p.append(result.p_value_used)
        pairwise.append(result)

    adjusted = holm_correction(raw_p) if raw_p else []
    pairwise = [
        PairwiseResult(pr.model_a, pr.model_b, pr.comparison, p_holm, pr.test)
        for pr, p_holm in zip(pairwise, adjusted, strict=True)
    ]

    edges = {frozenset((pr.model_a, pr.model_b)) for pr in pairwise if pr.p_holm >= alpha}
    groups = _maximal_cliques(order, edges)

    warnings = []
    if len({frozenset(qmap[m]) for m in models}) > 1:
        warnings.append(
            "The models were not scored on the same questions. Each mean is over that "
            "model's own questions; each paired test uses the questions its two models share."
        )
    if untested_pairs:
        warnings.append(
            f"{len(untested_pairs)} model pairs have fewer than two shared questions and cannot be tested. "
            "Untested pairs establish neither a difference nor equivalence."
        )
    return Leaderboard(
        entries=entries, pairwise=pairwise, groups=groups, alpha=alpha,
        untested_pairs=untested_pairs, warnings=warnings,
    )


def _summarize_mean(scores: list[float], confidence: float, use_wilson_below_n: int | None) -> MeanEstimate:
    """``use_wilson_below_n`` is None for averages of repeated generations, which are
    not binary trials even when every average happens to be 0 or 1."""
    n = len(scores)
    if use_wilson_below_n is not None and is_binary(scores):
        successes = int(round(sum(scores)))
        if prefer_wilson(successes, n, below_n=use_wilson_below_n):
            return wilson_ci(successes, n, confidence)
    return mean_ci_clt(scores, confidence)
