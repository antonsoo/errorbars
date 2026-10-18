"""Real native reducers must not silently become the arithmetic mean of epochs."""
from __future__ import annotations

from pathlib import Path

import pytest
from scipy.stats import binomtest, ttest_rel
from test_cli import run_cli

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.io import concat, load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.review import review_comparison

pytest.importorskip("inspect_ai")
from inspect_ai.log import read_eval_log, write_eval_log  # noqa: E402

CAPTURES = Path(__file__).resolve().parents[1] / "studies/inspect-reducers/captures"


def pair(label, **kwargs):
    return load_inputs([f"broad={CAPTURES / (label + '-broad.eval')}",
                        f"concentrated={CAPTURES / (label + '-concentrated.eval')}"], **kwargs).data


@pytest.mark.parametrize("reducer,expected", [("max", 1), ("pass_at_2", 2 / 3),
                                             ("median", 0), ("mode", 0), ("at_least_2", 0)])
def test_real_native_reductions_match_closed_form_and_independent_inference(reducer, expected):
    data = pair(reducer)
    assert len(data) == 48 and data.sample is None
    broad = data.filter_model("broad")
    assert broad.score == pytest.approx([expected] * 24)
    assert broad.question_hash and all(broad.question_hash)
    assert all(f"epoch reducer={reducer}; epochs=3" in r.name for r in broad.scoring)
    assert all("reductions[0].samples" in s.metric for s in broad.sources)
    review = review_comparison(data, "broad", "concentrated")
    assert review.comparison.mean_a == pytest.approx(expected)
    assert review.comparison.mean_b == .75
    if reducer == "pass_at_2":
        assert review.inference.test == "paired_t"
        assert review.inference.p_value == pytest.approx(ttest_rel(
            broad.score, data.filter_model("concentrated").score).pvalue)
    else:
        assert review.inference.test == "mcnemar_exact"
        discordant = 6 if expected == 1 else 18
        assert review.inference.p_value == binomtest(discordant, discordant, .5).pvalue
    assert review.cohort["n_identity_matching"] == 24
    assert all(f"epoch reducer={reducer}" in row["scorer"] for row in review.score_values)


@pytest.mark.parametrize("label", ["mean", "none"])
def test_mean_and_unreduced_controls_keep_raw_epochs_and_their_original_means(label):
    data = pair(label)
    assert len(data) == 144 and set(data.sample) == {"1", "2", "3"}
    assert data.filter_model("broad").scores_by_question() == {f"q{i:02}": 1 / 3 for i in range(24)}
    assert {rule.name for rule in data.scoring} == {"inspect:match"}
    assert build_leaderboard(data).entries[0].model == "concentrated"


def test_multiple_native_views_require_selection_and_preserve_both_valid_estimands():
    with pytest.raises(ValueError, match="multiple epoch reducers.*--inspect-reducer"):
        pair("mean-max")
    for name, winner, count in (("mean", "concentrated", 144), ("max", "broad", 48)):
        data = pair("mean-max", inspect_reducer=name)
        assert len(data) == count
        assert build_leaderboard(data).entries[0].model == winner
    with pytest.raises(ValueError, match="not recorded"):
        pair("mean-max", inspect_reducer="pass_at_2")


def test_actual_named_reductions_keep_the_selected_dimension_and_source_array():
    for key in ("correct", "loss"):
        data = pair("named-max", score_key=key)
        assert len(data) == 48 and data.filter_model("broad").score == [1] * 24
        assert all(rule.value_key == key for rule in data.scoring)
    with pytest.raises(ValueError, match="--score-key"):
        pair("named-max")


def test_rescored_view_takes_precedence_over_original_eval_configuration(tmp_path):
    log = read_eval_log(CAPTURES / "max-broad.eval")
    log.eval.config.epochs_reducer = ["mean"]
    path = tmp_path / "rescored.eval"
    write_eval_log(log, path)
    assert load_inspect_log(path).score == [1] * 24


@pytest.mark.parametrize("damage", ["missing", "duplicate", "unknown-id", "no-id", "no-reductions",
                                    "duplicate-view", "nonfinite", "bad-code", "changed-input"])
def test_damaged_reduction_or_raw_epoch_evidence_cannot_become_a_partial_result(tmp_path, damage):
    log = read_eval_log(CAPTURES / "max-broad.eval")
    view = log.reductions[0]
    if damage == "missing":
        view.samples.pop()
    elif damage == "duplicate":
        view.samples[-1].sample_id = view.samples[0].sample_id
    elif damage == "unknown-id":
        view.samples[-1].sample_id = "unrecorded-question"
    elif damage == "no-id":
        view.samples[-1].sample_id = None
    elif damage == "no-reductions":
        log.reductions = None
    elif damage == "duplicate-view":
        log.reductions.append(view.model_copy(deep=True))
    elif damage in ("nonfinite", "bad-code"):
        view.samples[-1].value = float("nan") if damage == "nonfinite" else "not-a-grade"
    else:
        next(sample for sample in log.samples if sample.id == "q00" and sample.epoch == 2).input = "changed"
    path = tmp_path / "damaged.eval"
    write_eval_log(log, path)
    with pytest.raises(ValueError):
        load_inspect_log(path)


def test_reduction_and_attempt_budget_survive_csv_and_block_incompatible_pairing(tmp_path):
    a = load_inspect_log(CAPTURES / "max-broad.eval")
    b = load_inspect_log(CAPTURES / "mean-concentrated.eval")
    a.model, b.model = ["A"] * len(a), ["B"] * len(b)
    data = concat([("a", a), ("b", b)])
    write_csv(data, tmp_path / "mixed.csv")
    for original in (data, load_csv(tmp_path / "mixed.csv")):
        review = review_comparison(original, "A", "B")
        assert review.comparison is None and review.cohort["n_scoring_conflicting"] == 24
    selected = pair("max")
    write_csv(selected, tmp_path / "max.csv")
    restored = load_csv(tmp_path / "max.csv")
    assert restored.score == selected.score and restored.scoring == selected.scoring
    assert review_comparison(restored, "broad", "concentrated").inference.p_value == .03125


def test_cli_selected_max_can_produce_report_and_normalized_scores(tmp_path):
    args = [f"broad={CAPTURES / 'mean-max-broad.eval'}",
            f"concentrated={CAPTURES / 'mean-max-concentrated.eval'}"]
    report = tmp_path / "max.html"
    result = run_cli("compare", *args, "--inspect-reducer", "max", "--html", str(report), "--json")
    assert result.returncode == 0, result.stderr
    assert '"mean_diff": 0.25' in result.stdout and report.is_file()
    assert "epoch reducer=max; epochs=3" in report.read_text()
    output = tmp_path / "max.csv"
    result = run_cli("import", "inspect", *args, "--inspect-reducer", "max", "-o", str(output))
    assert result.returncode == 0, result.stderr
    assert len(load_csv(output)) == 48
    with pytest.raises(ValueError, match="no Inspect log"):
        load_inputs([output], inspect_reducer="max")


@pytest.mark.parametrize("command", ["summarize", "compare", "leaderboard", "import"])
def test_ambiguous_native_view_preserves_existing_output_before_analysis(tmp_path, command):
    output = tmp_path / "previous.csv"
    output.write_bytes(b"previous result\n")
    args = [str(CAPTURES / "mean-max-broad.eval")]
    if command == "import":
        args = ["inspect", *args, "-o", str(output)]
    elif command != "summarize":
        args = [f"A={args[0]}", f"B={CAPTURES / 'mean-max-concentrated.eval'}", "--json"]
        args += ["--html" if command == "compare" else "--plot", str(output)]
    result = run_cli(command, *args)
    assert result.returncode == 1 and not result.stdout
    assert "--inspect-reducer" in result.stderr and "Traceback" not in result.stderr
    assert output.read_bytes() == b"previous result\n"
