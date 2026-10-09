"""Compare real Inspect captures and damaged copies through public import paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scipy.stats import ttest_rel
from test_cli import run_cli

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.io import load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import comparison_html
from errorbars.review import review_comparison

pytest.importorskip("inspect_ai")
from inspect_ai.log import EvalError, read_eval_log, write_eval_log  # noqa: E402
from inspect_ai.model import ChatMessageUser, ContentImage, ContentText  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "examples/inspect-comparison/logs"
SOURCE = LOGS / "original.eval"


def _pair(other):
    return load_inputs([f"A={SOURCE}", f"B={other}"]).data


def _changed(tmp_path, mutate, suffix=".eval"):
    log = read_eval_log(SOURCE)
    mutate(log)
    path = tmp_path / f"changed{suffix}"
    write_eval_log(log, path)
    return path


def test_real_solver_experiment_keeps_original_input_despite_different_message_ids():
    a, b = (read_eval_log(LOGS / f"{name}.eval") for name in ("original", "solver-variant"))
    assert a.samples[0].input[0].id != b.samples[0].input[0].id
    assert a.samples[0].input[0].content == b.samples[0].input[0].content
    assert a.samples[0].messages[0].role == "user"
    assert b.samples[0].messages[0].role == "system"
    review = review_comparison(_pair(LOGS / "solver-variant.eval"), "A", "B")
    assert review.cohort["n_identity_matching"] == review.comparison.n == 24
    scores_a = [float(sample.scores["match"].value == "C") for sample in a.samples]
    scores_b = [float(sample.scores["match"].value == "C") for sample in b.samples]
    assert review.comparison.mean_diff == pytest.approx(2 / 3)
    assert review.comparison.p_value == pytest.approx(ttest_rel(scores_a, scores_b).pvalue)


def test_actual_different_questions_no_longer_form_a_paired_win(tmp_path):
    data = _pair(LOGS / "different-questions.eval")
    review = review_comparison(data, "A", "B")
    assert review.comparison is None
    assert review.cohort["mean_difference"] is None
    assert review.cohort["n_identity_conflicting"] == 24
    assert all(q.difference is None for q in review.questions)
    with pytest.raises(ValueError, match="conflicting question content"):
        build_leaderboard(data)
    imported = tmp_path / "canonical.csv"
    write_csv(data, imported)
    assert load_csv(imported).pairing_conflicts("A", "B") == data.pairing_conflicts("A", "B")
    report = tmp_path / "conflict.html"
    result = run_cli("compare", f"A={SOURCE}", f"B={LOGS / 'different-questions.eval'}",
                     "--json", "--html", str(report))
    assert result.returncode == 1 and not result.stdout
    assert "conflicting question content" in result.stderr and "Traceback" not in result.stderr
    assert report.is_file() and "Inference unavailable" in report.read_text()


@pytest.mark.parametrize("field", ["input", "target", "choices"])
@pytest.mark.parametrize("suffix", [".eval", ".json"])
def test_changed_record_content_blocks_pairing_without_exporting_content(tmp_path, field, suffix):
    marker = "PRIVATE_CONTENT_MUST_NOT_LEAVE_THE_LOG"

    def mutate(log):
        setattr(log.samples[0], field, [marker] if field == "choices" else marker)

    data = _pair(_changed(tmp_path, mutate, suffix))
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_identity_conflicting"] == 1
    assert review.cohort["n_identity_matching"] == 23
    assert marker not in json.dumps(review.as_dict())
    assert marker not in comparison_html(review)


def test_resolved_text_attachments_match_inline_content_without_using_attachment_ids(tmp_path):
    def mutate(log):
        for sample in log.samples:
            content = sample.input[0].content
            sample.input = [ChatMessageUser(content=[ContentText(text="attachment://untrusted-id")])]
            sample.attachments["untrusted-id"] = content

    data = _pair(_changed(tmp_path, mutate))
    assert review_comparison(data, "A", "B").cohort["n_identity_matching"] == 24


@pytest.mark.parametrize("kind", ["image", "files", "setup", "empty-input", "empty-target", "dangling"])
def test_unsupported_or_unavailable_content_does_not_claim_verified_identity(tmp_path, kind):
    def mutate(log):
        sample = log.samples[0]
        if kind == "image":
            sample.input = [ChatMessageUser(content=[ContentImage(image="https://example.invalid/image")])]
        elif kind == "files":
            sample.files = ["dataset.csv"]
        elif kind == "setup":
            sample.setup = "load external task state"
        elif kind == "empty-input":
            sample.input = ""
        elif kind == "empty-target":
            sample.target = ""
        else:
            sample.input = "attachment://missing"

    review = review_comparison(_pair(_changed(tmp_path, mutate)), "A", "B")
    assert review.cohort["n_identity_unavailable"] == 1
    assert review.cohort["n_identity_matching"] == 23
    assert review.comparison is not None  # Unknown is not a known disagreement.


@pytest.mark.parametrize("name,n,questions", [("limited", 12, 12), ("selected-epochs", 6, 3)])
def test_real_limits_and_selected_epoch_runs_remain_complete(name, n, questions):
    data = load_inspect_log(LOGS / f"{name}.eval")
    assert len(data) == n and len(data.scores_by_question()) == questions
    assert len(data.question_hash) == n and all(data.question_hash)


@pytest.mark.parametrize("status", ["started", "cancelled", "error"])
def test_failed_run_is_rejected_even_when_every_retained_sample_is_scored(tmp_path, status):
    path = _changed(tmp_path, lambda log: setattr(log, "status", status))
    with pytest.raises(ValueError, match=f"status='{status}'"):
        load_inspect_log(path)


@pytest.mark.parametrize("damage", [
    "missing", "completed", "drained", "no-results", "invalidated", "sample-error",
    "extra-epoch", "no-epochs", "uneven-epochs", "swapped-id",
])
def test_incomplete_or_invalid_success_log_is_refused(tmp_path, damage):
    def mutate(log):
        if damage == "missing":
            log.samples.pop()
        elif damage == "completed":
            log.results.completed_samples -= 1
        elif damage == "drained":
            log.results.logged_samples = 2
        elif damage == "no-results":
            log.results = None
        elif damage == "invalidated":
            log.invalidated = True
        elif damage == "sample-error":
            log.samples[0].error = EvalError(message="failed", traceback="", traceback_ansi="")
        elif damage == "extra-epoch":
            log.samples[0].epoch = 2
        elif damage == "no-epochs":
            log.eval.config.epochs = 0
        elif damage == "uneven-epochs":
            log.eval.config.epochs = 2
        else:
            log.samples[0].id = "not-the-selected-question"

    path = _changed(tmp_path, mutate)
    with pytest.raises(ValueError):
        load_inspect_log(path)
    result = run_cli("summarize", str(path), "--json")
    assert result.returncode == 1 and not result.stdout and "Traceback" not in result.stderr


def test_changed_single_scorer_is_not_silently_pooled(tmp_path):
    def mutate(log):
        sample = log.samples[0]
        sample.scores = {"different_criterion": sample.scores["match"]}

    with pytest.raises(ValueError, match="scorer changed"):
        load_inspect_log(_changed(tmp_path, mutate))


def test_content_conflict_between_epochs_cannot_be_averaged(tmp_path):
    log = read_eval_log(LOGS / "selected-epochs.eval")
    # Log order can vary with asynchronous completion; locate the exact epoch.
    next(s for s in log.samples if s.id == "q02" and s.epoch == 2).target = "changed"
    path = tmp_path / "epochs.eval"
    write_eval_log(log, path)
    with pytest.raises(ValueError, match="conflicting question content across samples"):
        load_inspect_log(path)
