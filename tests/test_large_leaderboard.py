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


def test_a_long_board_prints_adjacent_ranks_and_rank_spans(tmp_path: Path) -> None:
    path = tmp_path / "board.csv"
    _board(path, [0.95 - 0.015 * i for i in range(60)])
    result = run_cli("leaderboard", str(path))
    assert result.returncode == 0, result.stderr
    assert "tied with ranks" in result.stdout
    assert "adjacent ranks (Holm-corrected over all 1770 pairs)" in result.stdout
    assert "Showing 59 adjacent-rank pairs of 1770" in result.stdout
    # 60 entries and 59 pairs, not 1,770 rows.
    assert len(result.stdout.splitlines()) < 200

    everything = run_cli("leaderboard", str(path), "--all-pairs")
    assert everything.returncode == 0, everything.stderr
    assert "adjacent ranks" not in everything.stdout
    assert len(everything.stdout.splitlines()) > 1770


def test_a_short_board_keeps_letters_and_every_pair(tmp_path: Path) -> None:
    path = tmp_path / "board.csv"
    _board(path, [0.8, 0.78, 0.6, 0.4])
    result = run_cli("leaderboard", str(path))
    assert result.returncode == 0, result.stderr
    assert "group" in result.stdout and "tied with ranks" not in result.stdout
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
