"""Multi-model leaderboards with paired pairwise tests and Holm correction."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Any, Literal

from errorbars._mean import IntervalStatus, summarize_mean
from errorbars.compare import PairedComparison, PairedTest, paired_compare, select_inference
from errorbars.io import EvalData
from errorbars.scoring import compare_scoring
from errorbars.stats import MeanEstimate

__all__ = [
    "LeaderboardEntry", "PairwiseResult", "UntestedPair", "Leaderboard",
    "build_leaderboard", "holm_correction", "rank_ranges",
]

# A modest number of models can have millions of overlapping maximal groups.
# These are report summaries; resource exhaustion must not discard inference.
_MAX_GROUPS = 4096
_MAX_GROUP_SEARCH_STATES = 50_000
GroupStatus = Literal["complete", "omitted_group_limit", "omitted_search_limit"]


class _GroupEnumerationLimitError(RuntimeError):
    def __init__(self, status: GroupStatus) -> None:
        super().__init__(status)
        self.status = status


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
    se: float | None
    ci_low: float | None
    ci_high: float | None
    n: int
    method: str
    n_observations: int = 0
    confidence: float = 0.95
    n_clusters: int | None = None
    dof_clustered: float | None = None
    unclustered: MeanEstimate | None = None
    warnings: list[str] = field(default_factory=list)
    interval_status: IntervalStatus = "available"

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
            "interval_status": self.interval_status,
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
    entries: list[LeaderboardEntry]  # sorted by mean in the declared score direction
    pairwise: list[PairwiseResult]
    groups: list[list[str]] | None  # Complete maximal groups, or unavailable; never a partial list.
    alpha: float
    untested_pairs: list[UntestedPair] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    group_status: GroupStatus = "complete"
    higher_is_better: bool = True
    direction_source: Literal["recorded", "explicit", "default"] = "default"

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
            "group_status": self.group_status,
            **({"group_limits": {"max_groups": _MAX_GROUPS,
                                  "max_search_states": _MAX_GROUP_SEARCH_STATES}}
               if self.group_status != "complete" else {}),
            "alpha": self.alpha,
            "higher_is_better": self.higher_is_better,
            "direction_source": self.direction_source,
            "rank_comparisons": self.rank_comparisons(),
            "untested_pairs": [asdict(pair) for pair in self.untested_pairs],
            "warnings": self.warnings,
        }


def _maximal_cliques(
    nodes: list[str], edges: set[frozenset[str]], *,
    max_groups: int = _MAX_GROUPS, max_search_states: int = _MAX_GROUP_SEARCH_STATES,
) -> list[list[str]]:
    """Bron-Kerbosch with pivoting (Tomita, Tanaka & Takahashi 2006).

    A leaderboard whose top entries are tied is close to one big clique, the
    worst case for the unpivoted algorithm: it took a minute for 28 real
    SWE-bench Verified submissions and did not finish for 47. Branching only
    on candidates outside the pivot's neighbourhood visits each maximal clique
    about once. Iterative, so a large tied group cannot exhaust the stack.
    The number of maximal cliques itself can still be exponential. Count both
    completed groups and visited search states; refuse the entire summary if
    either budget is exceeded, rather than publishing a biased partial list.
    """
    order = {v: i for i, v in enumerate(nodes)}
    adj: dict[str, set[str]] = {v: set() for v in nodes}
    for edge in edges:
        u, v = tuple(edge)
        adj[u].add(v)
        adj[v].add(u)

    cliques: list[set[str]] = []
    stack: list[tuple[set[str], set[str], set[str]]] = [(set(), set(nodes), set())]
    searched = 0
    while stack:
        if searched >= max_search_states:
            raise _GroupEnumerationLimitError("omitted_search_limit")
        searched += 1
        r, p, x = stack.pop()
        if not p:
            if not x:
                if len(cliques) >= max_groups:
                    raise _GroupEnumerationLimitError("omitted_group_limit")
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
    *,
    higher_is_better: bool | None = None,
) -> Leaderboard:
    """Build a leaderboard: per-model CIs, Holm-corrected pairwise tests, groups.

    ``use_wilson_below_n``: for binary scores with fewer than this many
    questions, or fewer than 10 successes or failures, per-model CIs use the
    Wilson interval instead of the CLT interval (see
    ``errorbars.stats.prefer_wilson``). With multi-question clusters, the
    displayed interval instead uses CR2 and Student t with effective degrees
    of freedom; the unclustered estimate is retained as a diagnostic. Means
    always weight questions equally, even with unequal numbers of generations.
    A model with insufficient independent units keeps its mean and counts,
    with None for its SE and interval and an explicit interval_status.

    Pairwise grouping uses clustered t when multiple shared questions belong to a
    cluster, exact McNemar for one binary observation per shared question
    without such clusters, and paired t for continuous or repeated-generation
    question means. The method is selected from the data structure, never
    from whichever test gives the smaller p-value. Holm is applied once to
    all selected raw p-values, including boards with mixed score types.
    A pair sharing fewer than two questions or fewer than two independent
    clusters remains untested; it does not prevent other pairs from being tested.
    If maximal group enumeration exceeds its count or search budget, groups is
    None and group_status explains the omission. All inference remains complete.

    Recorded score direction determines rank order. ``higher_is_better`` can
    supply a direction for undeclared scores, but cannot override contradictory
    input evidence. With neither, the historical higher-first order is used and
    explicitly labelled as a default. Scores and A - B differences keep their
    original units; selecting a rank direction never negates observations.
    """
    data.validate()
    models = data.models()
    if len(models) < 2:
        raise ValueError("leaderboard needs at least 2 models")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if higher_is_better is not None and type(higher_is_better) is not bool:
        raise ValueError("higher_is_better must be a boolean or None")
    directions = {value for value in data.higher_is_better or [] if value is not None}
    if len(directions) > 1:
        raise ValueError("conflicting score directions: a leaderboard requires one common direction")
    if directions and higher_is_better is not None and higher_is_better not in directions:
        raise ValueError("requested score direction conflicts with recorded higher_is_better evidence")
    direction_source: Literal["recorded", "explicit", "default"] = (
        "explicit" if higher_is_better is not None else "recorded" if directions else "default"
    )
    direction = higher_is_better if higher_is_better is not None else next(iter(directions), True)

    parts = {m: data.filter_model(m) for m in models}
    # The whole dataset was validated above; these parts only select its rows.
    # Revalidating each part repeats a full-data scan without new input evidence.
    qmap = {m: part._validated_question_means() for m, part in parts.items()}
    counts = {m: Counter(part.question_id) for m, part in parts.items()}
    n_observations = {m: len(part) for m, part in parts.items()}
    # Index content evidence once per board. Looking up both models in all rows
    # for every pair made validation cubic in model count on harness exports.
    hashes = {m: part.hashes_by_question(m) for m, part in parts.items()}
    cluster_of_q = data.cluster_by_question()

    entries: list[LeaderboardEntry] = []
    for m in models:
        scores = list(qmap[m].values())
        repeated = n_observations[m] > len(scores)
        clusters = [cluster_of_q[q] for q in qmap[m]] if cluster_of_q else None
        est = summarize_mean(
            scores, repeated=repeated, clusters=clusters, confidence=confidence,
            use_wilson_below_n=use_wilson_below_n,
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
                n_clusters=est.n_clusters,
                dof_clustered=est.dof_clustered,
                unclustered=est.unclustered,
                warnings=est.warnings,
                interval_status=est.interval_status,
            )
        )
    entries.sort(key=lambda e: e.mean, reverse=direction)
    order = [e.model for e in entries]

    # Align questions for paired tests: use the intersection of question_ids
    # common to both models, sorted for determinism.
    pairwise: list[PairwiseResult] = []
    untested_pairs: list[UntestedPair] = []
    raw_p: list[float] = []
    # Group declarations once; rescanning every observation for every model pair
    # makes this check cubic in the number of models.
    scoring = data.scoring_by_model() if data.scoring is not None else {}
    for a, b in combinations(order, 2):
        conflicts = sorted(q for q in hashes[a].keys() & hashes[b].keys() if hashes[a][q] != hashes[b][q])
        if conflicts:
            raise ValueError(
                f"{a!r} vs {b!r}: conflicting question content for {len(conflicts)} shared ids "
                f"(including {conflicts[0]!r}); inspect the source records before pairing"
            )
        scoring_conflicts = [
            q for q, state in compare_scoring(scoring.get(a, {}), scoring.get(b, {})).items()
            if state == "conflicting"
        ]
        if scoring_conflicts:
            raise ValueError(
                f"{a!r} vs {b!r}: conflicting scoring rules for {len(scoring_conflicts)} shared ids "
                f"(including {scoring_conflicts[0]!r}); re-score both runs under the same "
                "scorer and parameters before ranking"
            )
        common = sorted(set(qmap[a]) & set(qmap[b]))
        if len(common) < 2:
            untested_pairs.append(UntestedPair(a, b, len(common)))
            continue
        sa = [qmap[a][q] for q in common]
        sb = [qmap[b][q] for q in common]
        clusters = [cluster_of_q[q] for q in common] if cluster_of_q else None
        if clusters is not None and len(set(clusters)) < 2:
            untested_pairs.append(UntestedPair(a, b, len(common), "fewer_than_two_shared_clusters"))
            continue
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
    warnings = []
    missing_direction = sum(value is None for value in data.higher_is_better or [])
    if directions and missing_direction and higher_is_better is None:
        warnings.append(
            f"Score direction is unrecorded for {missing_direction} observations; "
            "ranking assumes they use the same direction as the recorded scores."
        )
    groups: list[list[str]] | None
    group_status: GroupStatus = "complete"
    try:
        groups = _maximal_cliques(order, edges)
    except _GroupEnumerationLimitError as exc:
        groups, group_status = None, exc.status
        limit = (
            f"exceeded the {_MAX_GROUPS:,}-group summary limit"
            if group_status == "omitted_group_limit"
            else f"reached the {_MAX_GROUP_SEARCH_STATES:,}-state search limit"
        )
        warnings.append(
            f"Overlapping non-significance groups were omitted because enumeration {limit}. "
            "Every model estimate, pairwise test and exact rank comparison is retained; "
            "this does not change any significance decision."
        )
    if data.scoring is not None:
        warnings.append(
            "Scoring checks reject conflicting recorded names or configurations on shared questions. "
            "Missing declarations remain unchecked; matching declarations do not verify scorer code "
            "or unrecorded settings."
        )
    if len({frozenset(qmap[m]) for m in models}) > 1:
        warnings.append(
            "The models were not scored on the same questions. Each mean is over that "
            "model's own questions; each paired test uses the questions its two models share."
        )
    if untested_pairs:
        reasons = Counter(pair.reason for pair in untested_pairs)
        details = []
        if reasons["fewer_than_two_shared_questions"]:
            details.append(
                f"{reasons['fewer_than_two_shared_questions']} with fewer than two shared questions"
            )
        if reasons["fewer_than_two_shared_clusters"]:
            details.append(
                f"{reasons['fewer_than_two_shared_clusters']} with only one shared independent cluster"
            )
        warnings.append(
            f"{len(untested_pairs)} model pairs cannot be tested: {'; '.join(details)}. "
            "Untested pairs establish neither a difference nor equivalence."
        )
    return Leaderboard(
        entries=entries, pairwise=pairwise, groups=groups, alpha=alpha,
        untested_pairs=untested_pairs, warnings=warnings, group_status=group_status,
        higher_is_better=direction, direction_source=direction_source,
    )
