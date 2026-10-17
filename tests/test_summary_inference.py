"""Primary summary uncertainty must follow independent units in the input."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from oracles import cr2_mean_oracle
from scipy.stats import t
from test_cli import run_cli

from errorbars.io import load_csv

SOURCE = Path(__file__).resolve().parents[1] / "studies/insufficient-cohorts/scores.csv"
MODEL = "20251205_sonar-foundation-agent_claude-opus-4-5"


def test_retained_submission_uses_the_dense_cr2_oracle_as_the_primary_summary() -> None:
    data = load_csv(SOURCE).filter_model(MODEL)
    means = data.scores_by_question()
    cluster_map = data.cluster_by_question()
    se, dof = cr2_mean_oracle(list(means.values()), [cluster_map[q] for q in means])
    mean = float(np.mean(list(means.values())))
    half_width = t.ppf(0.975, dof) * se
    result = run_cli("summarize", str(SOURCE), "--model", MODEL, "--json")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mean"] == mean
    assert summary["n"] == summary["n_questions"] == summary["n_observations"] == 500
    assert summary["method"] == "clustered_cr2" and summary["interval_status"] == "available"
    assert summary["n_clusters"] == 12
    assert summary["dof_clustered"] == pytest.approx(dof, rel=1e-12)
    assert summary["se"] == pytest.approx(se, rel=1e-12)
    assert summary["ci_low"] == pytest.approx(mean - half_width, abs=1e-12)
    assert summary["ci_high"] == pytest.approx(mean + half_width, abs=1e-12)
    assert summary["unclustered"]["method"] == "clt"
    assert summary["se"] > summary["unclustered"]["se"]
    assert summary["ci_low"] == summary["clustered"]["clustered_ci_low"]


def test_one_recorded_group_keeps_its_observed_mean_without_an_independent_primary_interval() -> None:
    result = run_cli("summarize", str(SOURCE), "--model", "django-only", "--json")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mean"] == pytest.approx(191 / 231)
    assert summary["n"] == 231 and summary["n_clusters"] == 1
    assert summary["interval_status"] == "fewer_than_two_clusters"
    assert summary["method"] == "unavailable"
    assert summary["se"] is summary["ci_low"] is summary["ci_high"] is None
    assert summary["clustered"]["icc"] is summary["clustered"]["design_effect"] is None
    assert summary["unclustered"]["ci_low"] is not None
    terminal = run_cli("summarize", str(SOURCE), "--model", "django-only")
    assert terminal.returncode == 0, terminal.stderr
    assert "unavailable" in terminal.stdout and "Only one independent cluster" in terminal.stdout


@pytest.mark.parametrize("scores", [[0.3], [1.0, 1.0, 1.0], [0.0, 1.0]])
def test_one_continuous_or_repeated_question_keeps_only_a_descriptive_mean(tmp_path, scores) -> None:
    source = tmp_path / "single.csv"
    source.write_text("question_id,model,score,sample\n" + "".join(
        f"q,m,{score},{i}\n" for i, score in enumerate(scores)
    ))
    result = run_cli("summarize", str(source), "--json")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mean"] == pytest.approx(np.mean(scores))
    assert summary["n"] == 1 and summary["n_observations"] == len(scores)
    assert summary["interval_status"] == "fewer_than_two_questions"
    assert summary["se"] is summary["ci_low"] is summary["ci_high"] is None
    assert "within_between" not in summary  # One question cannot estimate between-question variation.


def test_one_independent_binary_answer_keeps_the_existing_wilson_interval(tmp_path) -> None:
    source = tmp_path / "single.csv"
    source.write_text("question_id,model,score\nq,m,1\n")
    result = run_cli("summarize", str(source), "--json")
    summary = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert summary["method"] == "wilson" and summary["interval_status"] == "available"
    assert summary["ci_low"] == pytest.approx(0.2065493144)
    assert summary["ci_high"] == pytest.approx(1.0)


def test_repetition_counts_do_not_reweight_questions_or_override_supplied_clusters(tmp_path) -> None:
    source = tmp_path / "repeats.csv"
    source.write_text(
        "question_id,model,score,cluster_id,sample\n"
        + "".join(f"q1,m,0,passage,{i}\n" for i in range(12))
        + "q2,m,1,passage,0\nq3,m,1,passage,0\n"
    )
    result = run_cli("summarize", str(source), "--json")
    summary = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert summary["mean"] == pytest.approx(2 / 3)  # Not the observation-weighted 2/14.
    assert summary["n"] == 3 and summary["n_observations"] == 14
    assert summary["interval_status"] == "fewer_than_two_clusters"
    assert summary["unclustered"]["method"] == "clt"


@pytest.mark.parametrize("confidence", ["0", "1", "nan"])
def test_descriptive_summary_still_validates_requested_confidence(tmp_path, confidence) -> None:
    source = tmp_path / "single.csv"
    source.write_text("question_id,model,score\nq,m,0.3\n")
    result = run_cli("summarize", str(source), "--confidence", confidence, "--json")
    assert result.returncode != 0 and "confidence" in result.stderr
