"""Leaderboards the size of a public one: dozens of models, most of them near-tied."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from test_cli import run_cli

from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard
from errorbars.stats import prefer_wilson


def _board(path: Path, accuracies: list[float], n: int = 300, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    difficulty = rng.random(n)
    lines = ["question_id,model,score"]
    for m, accuracy in enumerate(accuracies):
        # A shared difficulty per question keeps the models correlated, as real ones are.
        solved = difficulty * 0.6 + rng.random(n) * 0.4 < np.quantile(difficulty * 0.6 + 0.2, accuracy)
        lines += [f"q{q},model-{m:02d},{int(s)}" for q, s in enumerate(solved)]
    path.write_text("\n".join(lines) + "\n")


def test_a_long_board_prints_adjacent_pairs_and_exact_rank_sets(tmp_path: Path) -> None:
    path = tmp_path / "board.csv"
    _board(path, [0.95 - 0.015 * i for i in range(60)])
    result = run_cli("leaderboard", str(path))
    assert result.returncode == 0, result.stderr
    assert "not separated: ranks" in result.stdout
    assert "adjacent ranks (Holm-corrected over all 1770 pairs)" in result.stdout
    assert "Showing 59 adjacent-rank pairs of 1770" in result.stdout
    # 60 entries and 59 pairs, not 1,770 rows.
    assert len(result.stdout.splitlines()) < 200

    everything = run_cli("leaderboard", str(path), "--all-pairs")
    assert everything.returncode == 0, everything.stderr
    assert "adjacent ranks" not in everything.stdout
    assert len(everything.stdout.splitlines()) > 1770


def test_a_short_board_prints_exact_ranks_and_every_pair(tmp_path: Path) -> None:
    path = tmp_path / "board.csv"
    _board(path, [0.8, 0.78, 0.6, 0.4])
    result = run_cli("leaderboard", str(path))
    assert result.returncode == 0, result.stderr
    assert "not separated: ranks" in result.stdout and "tied with ranks" not in result.stdout
    assert "adjacent ranks" not in result.stdout


def test_scores_near_zero_or_one_get_an_interval_inside_the_unit_range() -> None:
    n = 500
    scores = {"strong": [1.0] * 400 + [0.0] * 100, "weak": [1.0] * 2 + [0.0] * 498, "none": [0.0] * n}
    data = EvalData(
        question_id=[f"q{i}" for _ in scores for i in range(n)],
        model=[m for m in scores for _ in range(n)],
        score=[s for values in scores.values() for s in values],
    )
    entries = {e.model: e for e in build_leaderboard(data).entries}
    assert entries["strong"].method == "clt"
    for name in ("weak", "none"):
        assert entries[name].method == "wilson"
        assert 0.0 <= entries[name].ci_low <= entries[name].ci_high <= 1.0
    assert entries["none"].ci_high > 0.0


def test_wilson_is_preferred_for_few_questions_or_few_successes_or_failures() -> None:
    assert prefer_wilson(10, 20)
    assert prefer_wilson(2, 500) and prefer_wilson(498, 500)
    assert not prefer_wilson(124, 200) and not prefer_wilson(10, 500)


def test_rank_sets_preserve_significant_and_untested_holes() -> None:
    import json

    from errorbars.inputs import load_inputs
    from errorbars.leaderboard import rank_ranges

    path = Path(__file__).resolve().parents[1] / "examples/leaderboard-ranks/gaps.csv"
    board = build_leaderboard(load_inputs([path]).data)
    ranks = board.rank_comparisons()
    assert ranks["leader"] == {"non_significant": [2, 5], "significant": [4], "untested": [3]}
    assert ranks["unmatched"] == {"non_significant": [], "significant": [], "untested": [1, 2, 4, 5]}
    assert rank_ranges(ranks["leader"]["non_significant"]) == "2, 5"
    assert rank_ranges(ranks["unmatched"]["untested"]) == "1-2, 4-5"
    assert rank_ranges([]) == "-"
    for rank, entry in enumerate(board.entries, 1):
        sets = [set(values) for values in ranks[entry.model].values()]
        assert set.union(*sets) == set(range(1, 6)) - {rank}
        assert sum(len(values) for values in sets) == 4
    assert all(pair.n_shared == 0 for pair in board.untested_pairs)
    assert len(board.untested_pairs) == 4
    assert len(board.warnings) == 2

    result = run_cli("leaderboard", str(path), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rank_comparisons"] == ranks
    assert payload["warnings"] == board.warnings
    assert payload["untested_pairs"] == [
        {"model_a": pair.model_a, "model_b": pair.model_b, "n_shared": 0,
         "reason": "fewer_than_two_shared_questions"}
        for pair in board.untested_pairs
    ]
    text = run_cli("leaderboard", str(path)).stdout
    assert "not tested: ranks" in text
    assert "2, 5" in text
    assert "shared n" in text


def test_one_shared_question_is_untested_not_a_zero_variance_win() -> None:
    board = build_leaderboard(EvalData(
        ["shared", "a-only", "shared", "b-only"], ["a", "a", "b", "b"], [1., 1., 0., 0.]
    ))
    assert not board.pairwise
    assert board.rank_comparisons()["a"] == {"non_significant": [], "significant": [], "untested": [2]}
    assert board.untested_pairs[0].n_shared == 1
