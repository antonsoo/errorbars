"""Incomplete runs must not erase valid inference for the complete runs."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from oracles import cr2_mean_oracle
from scipy.stats import t
from test_cli import run_cli

from errorbars.io import EvalData, load_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.plot import forest_plot_matplotlib, forest_plot_svg

STUDY = Path(__file__).resolve().parents[1] / "studies/insufficient-cohorts"


def test_django_only_run_preserves_complete_runs_and_oracle_inference() -> None:
    data = load_csv(STUDY / "scores.csv")
    board = build_leaderboard(data)
    missing = next(e for e in board.entries if e.model == "django-only")
    assert missing.n == missing.n_observations == 231
    assert missing.mean == pytest.approx(np.mean(data.filter_model("django-only").score))
    assert missing.n_clusters == 1 and missing.dof_clustered is None
    assert missing.interval_status == "fewer_than_two_clusters"
    assert missing.se is missing.ci_low is missing.ci_high is None
    assert missing.unclustered is not None  # Labelled diagnostic, never the displayed interval.
    assert all("django-only" not in group or len(group) == 1 for group in board.groups)
    assert len(board.untested_pairs) == 2
    assert all(p.reason == "fewer_than_two_shared_clusters" and p.n_shared == 231
               for p in board.untested_pairs)

    before = json.loads((STUDY / "results/complete-before.json").read_text())
    complete = [e.as_dict() for e in board.entries if e.model != "django-only"]
    for entry in complete:
        assert entry.pop("interval_status") == "available"
    assert complete == before["entries"]
    assert [p.as_dict() for p in board.pairwise] == before["pairwise"]

    cmap = data.cluster_by_question()
    for entry in board.entries:
        if entry.model == "django-only":
            continue
        scores = data.filter_model(entry.model).scores_by_question()
        se, df = cr2_mean_oracle(list(scores.values()), [cmap[q] for q in scores])
        half = float(t.ppf(0.975, df)) * se
        assert entry.se == pytest.approx(se, rel=1e-10)
        assert entry.ci_low == pytest.approx(entry.mean - half, rel=1e-10)
        assert entry.ci_high == pytest.approx(entry.mean + half, rel=1e-10)


@pytest.mark.parametrize("scores", [[0.25], [0., 1.], [1.] * 12])
def test_one_question_continuous_or_repeated_keeps_only_a_descriptive_mean(scores: list[float]) -> None:
    data = EvalData(
        ["q1"] * len(scores) + ["q1", "q2"], ["partial"] * len(scores) + ["complete"] * 2,
        scores + [0.1, 0.7], sample=[str(i) for i in range(len(scores))] + ["0", "0"],
    )
    board = build_leaderboard(data)
    entry = next(e for e in board.entries if e.model == "partial")
    assert entry.mean == pytest.approx(np.mean(scores))
    assert entry.n == 1 and entry.n_observations == len(scores)
    assert entry.interval_status == "fewer_than_two_questions"
    assert entry.se is entry.ci_low is entry.ci_high is None
    assert entry.unclustered is None
    assert len(board.untested_pairs) == 1 and not board.pairwise
    assert board.untested_pairs[0].reason == "fewer_than_two_shared_questions"


def test_one_binary_observation_still_has_a_wilson_interval() -> None:
    board = build_leaderboard(EvalData(["q", "q"], ["a", "b"], [1., 0.]))
    assert all(e.method == "wilson" and e.interval_status == "available" for e in board.entries)


def test_descriptive_cluster_mean_still_weights_questions_equally() -> None:
    data = EvalData(
        ["q1"] * 12 + ["q2", "q3"] + ["q1", "q2", "q3"],
        ["repeated"] * 14 + ["other"] * 3, [0.] * 12 + [1., 1.] + [0.5] * 3,
        ["passage"] * 17, [str(i) for i in range(12)] + ["0"] * 5,
    )
    entry = next(e for e in build_leaderboard(data).entries if e.model == "repeated")
    assert entry.mean == pytest.approx(2 / 3)  # The observation-weighted mean would be 2/14.
    assert entry.n == 3 and entry.n_observations == 14
    assert entry.interval_status == "fewer_than_two_clusters"


@pytest.mark.parametrize("confidence", [0., 1., float("nan")])
def test_all_descriptive_board_still_validates_confidence(confidence: float) -> None:
    data = EvalData(["q", "q"], ["a", "b"], [0.2, 0.4])
    with pytest.raises(ValueError, match="confidence"):
        build_leaderboard(data, confidence=confidence)


def test_unavailable_interval_does_not_hide_content_conflicts() -> None:
    data = EvalData(["q", "q"], ["a", "b"], [0.2, 0.4], question_hash=["one", "different"])
    with pytest.raises(ValueError, match="conflicting question content"):
        build_leaderboard(data)


def test_cli_writes_null_intervals_and_usable_table_and_svg(tmp_path: Path) -> None:
    plot = tmp_path / "board.svg"
    result = run_cli("leaderboard", str(STUDY / "scores.csv"), "--json", "--plot", str(plot))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    entry = next(e for e in payload["entries"] if e["model"] == "django-only")
    assert entry["se"] is entry["ci_low"] is entry["ci_high"] is None
    assert "NaN" not in result.stdout and "Infinity" not in result.stdout
    svg = ET.fromstring(plot.read_text())
    ns = {"s": "http://www.w3.org/2000/svg"}
    row = next(g for g in svg.findall("s:g", ns) if g.find("s:title", ns).text == "django-only")
    assert not row.findall("s:line", ns)  # No bar or caps masquerading as a point interval.
    assert row.find("s:circle", ns).attrib["fill"] == "#ffffff"
    assert "CI unavailable" in " ".join(row.itertext())
    text = run_cli("leaderboard", str(STUDY / "scores.csv"))
    assert text.returncode == 0, text.stderr
    assert "unavailable" in text.stdout and "only 1 cluster" in text.stdout


def test_all_descriptive_plots_remain_finite_and_have_no_error_bars() -> None:
    board = build_leaderboard(EvalData(["q", "q"], ["a", "b"], [0.2, 0.4]))
    svg = forest_plot_svg(board)
    assert "nan" not in svg.lower() and 'x1="inf' not in svg.lower()
    assert svg.count("CI unavailable") == 3  # Two rows and caption.
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = forest_plot_matplotlib(board)
    ax = fig.axes[0]
    assert len(ax.lines) == 2 and not ax.containers
    assert [text.get_text() for text in ax.texts] == ["CI unavailable"] * 2
    plt.close(fig)
