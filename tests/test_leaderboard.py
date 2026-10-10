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


def _clustered_board() -> EvalData:
    rng = np.random.default_rng(3)
    question_id, model, score, cluster = [], [], [], []
    for q in range(60):
        base = rng.random()
        for name, lift in (("a", 0.0), ("b", 0.1), ("c", 0.2)):
            question_id.append(f"q{q}")
            model.append(name)
            score.append(float(rng.random() < 0.3 + lift + 0.3 * base))
            cluster.append(f"passage-{q // 5}")
    return EvalData(question_id, model, score, cluster_id=cluster)


def test_pairwise_rows_carry_the_p_value_the_holm_correction_used() -> None:
    board = build_leaderboard(_clustered_board())
    rows = [pr.as_dict() for pr in board.pairwise]
    assert all(row["p_value_clustered"] is not None for row in rows)
    assert [row["p_holm"] for row in rows] == pytest.approx(
        holm_correction([row["p_value_clustered"] for row in rows])
    )


def test_unclustered_pairwise_rows_have_no_clustered_p_value() -> None:
    data = _clustered_board()
    data.cluster_id = None
    assert all(pr.as_dict()["p_value_clustered"] is None for pr in build_leaderboard(data).pairwise)


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, 2.0, float("nan")])
def test_alpha_outside_zero_to_one_is_rejected(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha must be in"):
        build_leaderboard(_clustered_board(), alpha=alpha)


def test_two_binary_wins_do_not_establish_a_winner() -> None:
    data = EvalData(["q1", "q2"] * 2, ["candidate"] * 2 + ["baseline"] * 2, [1.0, 1.0, 0.0, 0.0])
    board = build_leaderboard(data)
    (pair,) = board.pairwise
    assert pair.comparison.p_value == 0  # Retained paired-t diagnostic, not selected.
    assert pair.test == "mcnemar_exact"
    assert pair.p_value_used == pair.p_holm == 0.5
    assert board.groups == [["candidate", "baseline"]]
    row = pair.as_dict()
    assert row["test"] == "mcnemar_exact"
    assert row["p_value_used"] == 0.5
    assert row["mcnemar"] == {"n01": 0, "n10": 2, "p_value": 0.5}


def test_exact_binary_board_matches_oracle_for_every_small_discordant_table() -> None:
    import math

    from statsmodels.stats.contingency_tables import mcnemar

    for discordants in range(21):
        rejection_probability = 0.0
        for n01 in range(discordants + 1):
            n10 = discordants - n01
            # Add concordant pairs: the exact result must only use discordants.
            a = [0.0] * n01 + [1.0] * n10 + [1.0, 0.0]
            b = [1.0] * n01 + [0.0] * n10 + [1.0, 0.0]
            questions = [f"q{i}" for i in range(len(a))]
            board = build_leaderboard(EvalData(questions * 2, ["a"] * len(a) + ["b"] * len(b), a + b))
            (pair,) = board.pairwise
            expected = mcnemar([[1, n01], [n10, 1]], exact=True).pvalue
            assert pair.test == "mcnemar_exact"
            assert pair.p_holm == pytest.approx(expected, abs=1e-14)
            if pair.p_holm < 0.05:
                rejection_probability += math.comb(discordants, n01) / 2**discordants
        assert rejection_probability <= 0.05


def test_cluster_dependence_takes_precedence_over_binary_outcomes() -> None:
    board = build_leaderboard(_clustered_board())
    assert all(pair.test == "clustered_t" for pair in board.pairwise)
    assert all(pair.p_value_used == pair.comparison.p_value_clustered for pair in board.pairwise)


def test_singleton_cluster_labels_still_allow_exact_binary_pairing() -> None:
    data = EvalData(["q1", "q2"] * 2, ["a"] * 2 + ["b"] * 2, [1.0, 1.0, 0.0, 0.0], ["c1", "c2"] * 2)
    (pair,) = build_leaderboard(data).pairwise
    assert pair.test == "mcnemar_exact"
    assert pair.p_holm == 0.5


def test_repeated_generation_means_do_not_become_binary_trials() -> None:
    # Observed means happen to be exactly 0/1; each still averages two draws.
    data = EvalData(
        ["q1", "q1", "q2", "q2"] * 2,
        ["a"] * 4 + ["b"] * 4,
        [1.0] * 4 + [0.0] * 4,
        sample=["0", "1", "0", "1"] * 2,
    )
    (pair,) = build_leaderboard(data).pairwise
    assert pair.test == "paired_t"
    assert pair.p_value_used == pair.comparison.p_value
    assert pair.comparison.warnings  # Degeneracy remains explicit.


def test_unmatched_repeated_generations_do_not_change_the_shared_test() -> None:
    data = EvalData(
        ["q1", "q2", "q3", "q3", "q1", "q2"],
        ["a"] * 4 + ["b"] * 2,
        [1.0] * 4 + [0.0] * 2,
        sample=["0", "0", "0", "1", "0", "0"],
    )
    (pair,) = build_leaderboard(data).pairwise
    assert pair.test == "mcnemar_exact"
    assert pair.p_holm == 0.5


def test_mixed_score_board_has_one_holm_family() -> None:
    scores = {
        "binary-a": [1.0, 1.0, 1.0, 1.0, 0.0, 1.0],
        "binary-b": [0.0, 0.0, 1.0, 0.0, 0.0, 1.0],
        "continuous": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    }
    data = EvalData(
        [f"q{i}" for _ in scores for i in range(6)],
        [m for m in scores for _ in range(6)],
        [v for values in scores.values() for v in values],
    )
    pairs = build_leaderboard(data).pairwise
    assert sorted(p.test for p in pairs) == ["mcnemar_exact", "paired_t", "paired_t"]
    _, expected, _, _ = multipletests([p.p_value_used for p in pairs], method="holm")
    assert [p.p_holm for p in pairs] == pytest.approx(expected)


@pytest.mark.parametrize("sizes", [[4, 4, 4, 4], [12, 4, 2, 1]])
@pytest.mark.parametrize("confidence", [0.9, 0.95, 0.99])
def test_displayed_clustered_intervals_match_independent_matrix_oracle(
    sizes: list[int],
    confidence: float,
) -> None:
    from oracles import cr2_mean_oracle
    from scipy.stats import t

    rng = np.random.default_rng(73)
    clusters = [str(c) for c in np.repeat(np.arange(len(sizes)), sizes)]
    n = len(clusters)
    a = rng.normal(0.5, 0.1, n).tolist()
    b = rng.normal(0.4, 0.2, n).tolist()
    data = EvalData([f"q{i}" for i in range(n)] * 2, ["a"] * n + ["b"] * n, a + b, clusters * 2)
    board = build_leaderboard(data, confidence=confidence)
    for entry in board.entries:
        values = a if entry.model == "a" else b
        se, dof = cr2_mean_oracle(values, clusters)
        half = t.ppf((1 + confidence) / 2, dof) * se
        assert entry.method == "clustered_cr2"
        assert entry.confidence == confidence
        assert entry.n_clusters == len(sizes)
        assert entry.se == pytest.approx(se, rel=1e-10)
        assert entry.dof_clustered == pytest.approx(dof, rel=1e-10)
        # SciPy 1.11's inverse t at df=3, p=.995 differs from the closed-form
        # CDF inverse by ~1e-8 (about 3e-10 after scaling by this fixture's SE).
        # Keep this matrix-oracle check compatible with the supported floor.
        assert entry.ci_low == pytest.approx(entry.mean - half, abs=1e-9)
        assert entry.ci_high == pytest.approx(entry.mean + half, abs=1e-9)
        assert entry.unclustered is not None
        assert entry.unclustered.mean == entry.mean
        assert entry.as_dict()["unclustered"]["method"] == "clt"
        assert entry.warnings  # Fewer than ten effective degrees of freedom.


def test_cluster_intervals_count_questions_instead_of_generations() -> None:
    from oracles import cr2_mean_oracle

    questions, models, scores, clusters, samples = [], [], [], [], []
    means = {"a": [0.2, 0.8, 0.6], "b": [0.1, 0.4, 0.3]}
    for model in means:
        for question, repeats in enumerate([1, 3, 7]):
            for sample in range(repeats):
                questions.append(f"q{question}")
                models.append(model)
                scores.append(means[model][question])
                clusters.append("c1" if question < 2 else "c2")
                samples.append(str(sample))
    board = build_leaderboard(EvalData(questions, models, scores, clusters, samples))
    for entry in board.entries:
        se, dof = cr2_mean_oracle(means[entry.model], ["c1", "c1", "c2"])
        assert entry.mean == pytest.approx(np.mean(means[entry.model]))
        assert entry.n == 3 and entry.n_observations == 11
        assert entry.n_clusters == 2
        assert entry.se == pytest.approx(se)
        assert entry.dof_clustered == pytest.approx(dof)


def test_one_group_cannot_silently_fall_back_to_an_iid_interval() -> None:
    data = EvalData(["q1", "q2"] * 2, ["a"] * 2 + ["b"] * 2, [1.0, 0.0, 0.0, 1.0], ["one-passage"] * 4)
    with pytest.raises(ValueError, match="model 'a'.*at least 2 independent clusters"):
        build_leaderboard(data)


def test_singleton_clusters_preserve_existing_intervals() -> None:
    data = EvalData(["q1", "q2"] * 2, ["a"] * 2 + ["b"] * 2, [1.0, 1.0, 0.0, 0.0])
    before = build_leaderboard(data)
    data.cluster_id = ["c1", "c2"] * 2
    assert build_leaderboard(data).entries == before.entries
    assert all(e.method == "wilson" and e.unclustered is None for e in before.entries)
