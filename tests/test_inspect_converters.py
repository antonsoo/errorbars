"""A raw numeric grade can mean the opposite of a native accuracy observation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import run_cli

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.io import load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.review import review_comparison

pytest.importorskip("inspect_ai")
from inspect_ai.log import read_eval_log, write_eval_log  # noqa: E402

CAPTURES = Path(__file__).parents[1] / "studies/inspect-converters/captures"


@pytest.mark.parametrize("label,native,raw", [("perfect", 1, 0), ("wrong", 0, 1)])
def test_actual_native_numeric_converter_logs_refuse_default_substitution(label, native, raw):
    path = CAPTURES / f"reversed-{label}.eval"
    log = read_eval_log(path)
    assert log.status == "success"
    assert len(log.samples) == log.results.total_samples == 8
    assert log.results.scores[0].metrics["accuracy"].value == native
    assert all(sample.scores["reversed_grade"].value == raw for sample in log.samples)
    assert log.results.scores[0].metrics["accuracy"].params == {"to_float": "to_float"}
    with pytest.raises(ValueError, match="custom score conversion"):
        load_inspect_log(path)


def test_selected_named_value_does_not_borrow_another_dimensions_conversion(tmp_path):
    specs = [f"perfect={CAPTURES / 'named-perfect.eval'}", f"wrong={CAPTURES / 'named-wrong.eval'}"]
    with pytest.raises(ValueError, match="custom score conversion"):
        load_inputs(specs, score_key="reversed")
    data = load_inputs(specs, score_key="plain").data
    board = build_leaderboard(data)
    assert [(e.model, e.mean) for e in board.entries] == [("perfect", 1), ("wrong", 0)]
    review = review_comparison(data, "perfect", "wrong")
    assert review.inference.test == "mcnemar_exact"
    assert review.inference.p_value == 2 / 2**8
    write_csv(data, tmp_path / "plain.csv")
    assert load_csv(tmp_path / "plain.csv").score == data.score


def test_default_native_codes_keep_the_harness_accuracy_and_exact_test():
    data = load_inputs([f"perfect={CAPTURES / 'default-perfect.eval'}",
                        f"wrong={CAPTURES / 'default-wrong.eval'}"]).data
    assert data.filter_model("perfect").score == [1] * 8
    assert data.filter_model("wrong").score == [0] * 8
    assert build_leaderboard(data).entries[0].model == "perfect"


@pytest.mark.parametrize("command", ["summarize", "compare", "leaderboard", "import"])
def test_cli_refuses_before_inference_or_replacing_existing_exports(tmp_path, command):
    output = tmp_path / "previous.csv"
    output.write_bytes(b"previous result\n")
    path = CAPTURES / "reversed-perfect.eval"
    args = [str(path)]
    if command == "import":
        args = ["inspect", str(path), "-o", str(output)]
    elif command != "summarize":
        args = [f"perfect={path}", f"wrong={CAPTURES / 'reversed-wrong.eval'}", "--json"]
        args += ["--html" if command == "compare" else "--plot", str(output)]
    result = run_cli(command, *args)
    assert result.returncode == 1 and not result.stdout
    assert "custom score conversion" in result.stderr and "Traceback" not in result.stderr
    if command != "summarize":
        assert output.read_bytes() == b"previous result\n"


def test_result_converter_is_checked_even_when_scorer_parameters_are_unknown(tmp_path):
    log = read_eval_log(CAPTURES / "reversed-perfect.eval").model_dump(mode="json")
    del log["results"]["scores"][0]["params"]
    path = tmp_path / "missing-scorer-params.json"
    path.write_text(json.dumps(log))
    with pytest.raises(ValueError, match="custom score conversion"):
        load_inspect_log(path)


def test_explicit_default_callable_name_cannot_certify_its_closure(tmp_path):
    log = read_eval_log(CAPTURES / "default-perfect.eval")
    log.results.scores[0].metrics["accuracy"].params["to_float"] = "value_to_float"
    path = tmp_path / "opaque.eval"
    write_eval_log(log, path)
    with pytest.raises(ValueError, match="custom score conversion"):
        load_inspect_log(path)


def test_rescored_result_metadata_takes_precedence_over_original_scorer_declaration(tmp_path):
    # Native re-scoring may replace metric definitions; eval.scorers can be stale.
    log = read_eval_log(CAPTURES / "default-perfect.eval")
    declaration = read_eval_log(CAPTURES / "reversed-perfect.eval").eval.scorers[0]
    declaration.name = "default_grade"
    log.eval.scorers = [declaration]
    path = tmp_path / "rescored.eval"
    write_eval_log(log, path)
    assert load_inspect_log(path).score == [1] * 8
