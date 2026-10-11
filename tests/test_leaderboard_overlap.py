"""Partial evaluation cohorts can leave a pair with just one independent group."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from oracles import cr2_mean_oracle
from scipy.stats import t
from statsmodels.stats.multitest import multipletests
from test_cli import run_cli

from errorbars.io import EvalData, load_csv
from errorbars.leaderboard import build_leaderboard

FIXTURE = Path(__file__).resolve().parents[1] / "studies/leaderboard-overlap/partial-cohorts.csv"


def test_single_shared_cluster_keeps_the_rest_of_the_board_and_exact_rank_sets() -> None:
    data = load_csv(FIXTURE)
    board = build_leaderboard(data)
    assert len(board.entries) == 4
    assert len(board.pairwise) == len(board.untested_pairs) == 3
    assert {frozenset((pair.model_a, pair.model_b)) for pair in board.untested_pairs} == {
        frozenset(("model-a", "model-b")), frozenset(("model-a", "model-c")),
        frozenset(("model-b", "model-c")),
    }
    assert all(pair.n_shared == 10 for pair in board.untested_pairs)
    assert all(pair.reason == "fewer_than_two_shared_clusters" for pair in board.untested_pairs)
    assert any("only one shared independent cluster" in note for note in board.warnings)
    ranks = {entry.model: i for i, entry in enumerate(board.entries, 1)}
    for a in ("model-a", "model-b", "model-c"):
        assert board.rank_comparisons()[a]["untested"] == sorted(
            ranks[b] for b in ("model-a", "model-b", "model-c") if b != a
        )
    for group in board.groups:
        assert len(set(group) & {"model-a", "model-b", "model-c"}) <= 1

    # Independent matrix CR2 and scipy t reference, then statsmodels Holm over
    # the three eligible tests. Untestable pairs contribute no invented p-value.
    cmap = data.cluster_by_question()
    expected_p = []
    for pair in board.pairwise:
        a = data.filter_model(pair.model_a).scores_by_question()
        b = data.filter_model(pair.model_b).scores_by_question()
        common = sorted(a.keys() & b.keys())
        differences = [a[q] - b[q] for q in common]
        se, df = cr2_mean_oracle(differences, [cmap[q] for q in common])
        p = float(2 * t.sf(abs(sum(differences) / len(differences)) / se, df))
        expected_p.append(p)
        assert pair.test == "clustered_t"
        assert pair.comparison.n == 20
        assert pair.p_value_used == pytest.approx(p, abs=1e-12)
    assert [pair.p_holm for pair in board.pairwise] == pytest.approx(
        multipletests(expected_p, method="holm")[1], abs=1e-12,
    )


def test_mixed_unavailable_reasons_remain_distinct() -> None:
    data = load_csv(FIXTURE)
    data.question_id.extend(["elsewhere-1", "elsewhere-2"])
    data.model.extend(["isolated"] * 2)
    data.score.extend([0., 1.])
    assert data.cluster_id is not None and data.question_hash is not None
    data.cluster_id.extend(["elsewhere-1", "elsewhere-2"])
    data.question_hash.extend([None, None])
    assert data.sources is not None
    data.sources.extend([None, None])
    board = build_leaderboard(data)
    assert len(board.pairwise) == 3
    assert [pair.reason for pair in board.untested_pairs].count("fewer_than_two_shared_questions") == 4
    assert [pair.reason for pair in board.untested_pairs].count("fewer_than_two_shared_clusters") == 3


def test_no_eligible_clustered_pairs_still_produce_descriptive_model_estimates() -> None:
    data = load_csv(FIXTURE)
    keep = [i for i, model in enumerate(data.model) if model != "model-d"]
    assert data.cluster_id is not None
    board = build_leaderboard(EvalData(
        [data.question_id[i] for i in keep], [data.model[i] for i in keep],
        [data.score[i] for i in keep], [data.cluster_id[i] for i in keep],
    ))
    assert len(board.entries) == 3
    assert not board.pairwise
    assert len(board.untested_pairs) == 3
    assert all(len(group) == 1 for group in board.groups)


def test_conflicting_content_is_not_downgraded_to_an_untested_cluster_pair() -> None:
    data = load_csv(FIXTURE)
    assert data.question_hash is not None
    i = next(i for i, model in enumerate(data.model) if model == "model-b")
    data.question_hash[i] = "different-content"
    with pytest.raises(ValueError, match="conflicting question content"):
        build_leaderboard(data)


def test_partial_cohort_cli_json_table_and_svg(tmp_path: Path) -> None:
    plot = tmp_path / "partial.svg"
    result = run_cli("leaderboard", str(FIXTURE), "--json", "--plot", str(plot))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["entries"]) == 4
    assert len(payload["pairwise"]) == len(payload["untested_pairs"]) == 3
    assert all(pair["reason"] == "fewer_than_two_shared_clusters" for pair in payload["untested_pairs"])
    assert "not tested:" in plot.read_text()
    result = run_cli("leaderboard", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    assert "not tested: ranks" in result.stdout
    assert "only one shared independent cluster" in result.stdout
