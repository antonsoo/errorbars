from __future__ import annotations

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

from errorbars.io import EvalData
from errorbars.leaderboard import _maximal_cliques, build_leaderboard, holm_correction


@pytest.mark.parametrize(
    "p_values",
    [
        [0.001, 0.02, 0.03, 0.5],
        [0.5, 0.5, 0.5],
        [0.049, 0.051, 0.0001, 0.9, 0.2],
    ],
)
def test_holm_correction_matches_statsmodels(p_values: list[float]) -> None:
    ours = holm_correction(p_values)
    _, theirs, _, _ = multipletests(p_values, method="holm")
    assert ours == pytest.approx(list(theirs), abs=1e-12)


def test_maximal_cliques_simple_chain() -> None:
    # a-b edge, b-c edge, no a-c edge: cliques are {a,b} and {b,c}.
    nodes = ["a", "b", "c"]
    edges = {frozenset(("a", "b")), frozenset(("b", "c"))}
    cliques = _maximal_cliques(nodes, edges)
    clique_sets = {frozenset(c) for c in cliques}
    assert frozenset(("a", "b")) in clique_sets
    assert frozenset(("b", "c")) in clique_sets
    assert frozenset(("a", "c")) not in clique_sets


def test_maximal_cliques_fully_connected() -> None:
    nodes = ["a", "b", "c"]
    edges = {frozenset(("a", "b")), frozenset(("b", "c")), frozenset(("a", "c"))}
    cliques = _maximal_cliques(nodes, edges)
    assert len(cliques) == 1
    assert set(cliques[0]) == {"a", "b", "c"}


def _synthetic_eval_data(seed: int = 0) -> EvalData:
    rng = np.random.default_rng(seed)
    models = {"m1": 0.5, "m2": 0.5, "m3": 0.8}  # m1, m2 identical in truth; m3 clearly better
    question_id, model, score, cluster_id = [], [], [], []
    for q in range(150):
        cid = f"c{q // 5}"
        for m, p in models.items():
            question_id.append(f"q{q}")
            model.append(m)
            score.append(float(rng.uniform() < p))
            cluster_id.append(cid)
    return EvalData(question_id, model, score, cluster_id)


def test_build_leaderboard_end_to_end_ranks_and_groups() -> None:
    data = _synthetic_eval_data()
    lb = build_leaderboard(data, confidence=0.95, alpha=0.05)
    assert lb.entries[0].model == "m3"  # highest mean ranked first
    assert len(lb.entries) == 3
    # m1 and m2 have identical true means; they should land in a shared group.
    group_sets = [set(g) for g in lb.groups]
    assert any({"m1", "m2"} <= g for g in group_sets)
    # m3 should not share a group with m1 (clearly different in truth).
    assert not any({"m1", "m3"} <= g for g in group_sets)


def test_build_leaderboard_requires_two_models() -> None:
    data = EvalData(["q1", "q2"], ["only-model", "only-model"], [1.0, 0.0])
    with pytest.raises(ValueError):
        build_leaderboard(data)
