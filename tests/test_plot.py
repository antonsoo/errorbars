from __future__ import annotations

import re

from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard
from errorbars.plot import forest_plot_svg


def _sample_leaderboard():
    question_id, model, score, cluster_id = [], [], [], []
    import random

    rng = random.Random(0)
    for q in range(60):
        cid = f"c{q // 4}"
        for m, p in {"a": 0.4, "b": 0.6, "c": 0.6}.items():
            question_id.append(f"q{q}")
            model.append(m)
            score.append(1.0 if rng.random() < p else 0.0)
            cluster_id.append(cid)
    data = EvalData(question_id, model, score, cluster_id)
    return build_leaderboard(data)


def test_forest_plot_svg_is_well_formed_and_contains_all_models() -> None:
    lb = _sample_leaderboard()
    svg = forest_plot_svg(lb, title="Test Leaderboard")
    assert svg.startswith("<svg")
    assert svg.strip().endswith("</svg>")
    for entry in lb.entries:
        assert entry.model in svg
    # exactly one circle marker per model (the point estimate)
    assert len(re.findall(r"<circle", svg)) == len(lb.entries)
    assert "Test Leaderboard" in svg


def test_forest_plot_svg_escapes_model_names() -> None:
    question_id = ["q1", "q1", "q2", "q2"]
    model = ["<script>", "safe & sound", "<script>", "safe & sound"]
    score = [1.0, 0.0, 0.0, 1.0]
    data = EvalData(question_id, model, score)
    lb = build_leaderboard(data)
    svg = forest_plot_svg(lb)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
