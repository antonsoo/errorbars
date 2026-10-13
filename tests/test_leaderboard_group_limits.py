from __future__ import annotations

from itertools import combinations

import pytest

from errorbars.io import EvalData
from errorbars.leaderboard import (
    _GroupEnumerationLimitError,
    _maximal_cliques,
    build_leaderboard,
)


def test_every_five_node_graph_matches_exhaustive_maximal_subsets() -> None:
    nodes = [str(i) for i in range(5)]
    possible = [frozenset(pair) for pair in combinations(nodes, 2)]
    for mask in range(1 << len(possible)):
        edges = {edge for bit, edge in enumerate(possible) if mask & (1 << bit)}
        complete = [frozenset(group) for size in range(1, 6)
                    for group in combinations(nodes, size)
                    if all(frozenset(pair) in edges for pair in combinations(group, 2))]
        expected = {group for group in complete if not any(group < other for other in complete)}
        assert {frozenset(group) for group in _maximal_cliques(nodes, edges)} == expected


def test_group_budget_allows_exact_limit_but_never_returns_partial_groups() -> None:
    assert _maximal_cliques(["a", "b"], set(), max_groups=2) == [["a"], ["b"]]
    with pytest.raises(_GroupEnumerationLimitError, match="omitted_group_limit"):
        _maximal_cliques(["a", "b"], set(), max_groups=1)


def test_search_budget_allows_completion_at_limit() -> None:
    edges = {frozenset(("a", "b"))}
    assert _maximal_cliques(["a", "b"], edges, max_search_states=3) == [["a", "b"]]
    with pytest.raises(_GroupEnumerationLimitError, match="omitted_search_limit"):
        _maximal_cliques(["a", "b"], edges, max_search_states=2)


def test_exponential_group_summary_does_not_discard_any_inference() -> None:
    models, questions, scores = [], [], []
    # Independent balanced parity columns, each paired with 16 corrected answers.
    # Only each original/corrected pair separates after Holm; every cross-pair
    # edge remains, so there are exactly 2**25 maximal groups of 25 models.
    for pair in range(1, 26):
        remaining = 16
        for question in range(1024):
            base = (question & pair).bit_count() % 2
            corrected = base or remaining > 0
            remaining -= int(not base and remaining > 0)
            models.extend([f"{pair}:base", f"{pair}:corrected"])
            questions.extend([str(question)] * 2)
            scores.extend([float(base), float(corrected)])
    board = build_leaderboard(EvalData(questions, models, scores))
    assert len(board.entries) == 50
    assert len(board.pairwise) == 1225
    assert len(board.untested_pairs) == 0
    for pair in board.pairwise:
        same_pair = pair.model_a.split(":")[0] == pair.model_b.split(":")[0]
        assert pair.test == "mcnemar_exact"
        assert pair.p_holm == pytest.approx(1225 / 32768 if same_pair else 1)
    for row in board.rank_comparisons().values():
        assert len(row["significant"]) == 1
        assert len(row["non_significant"]) == 48
        assert row["untested"] == []
    assert board.groups is None
    assert board.group_status == "omitted_group_limit"
    exported = board.as_dict()
    assert exported["groups"] is None
    assert exported["group_status"] == "omitted_group_limit"
    assert exported["group_limits"]["max_groups"] == 4096
    assert any("Every model estimate, pairwise test" in note for note in board.warnings)
