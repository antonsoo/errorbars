"""Selected native score dimensions must remain distinct throughout analysis."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import run_cli

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.inputs import load_inputs
from errorbars.io import ColumnMap, EvalData, ScoringRule, concat, load_csv, load_jsonl, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.review import review_comparison

pytest.importorskip("inspect_ai")
from inspect_ai.log import read_eval_log, write_eval_log  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures/inspect_tiny_named_values.eval"


def change(tmp_path, mutate):
    log = read_eval_log(FIXTURE)
    mutate(log)
    path = tmp_path / "changed.eval"
    write_eval_log(log, path)
    return path


def test_actual_sdk_dictionary_values_select_independently_and_do_not_guess():
    log = read_eval_log(FIXTURE)
    for key in ("length", "has_digit"):
        data = load_inspect_log(FIXTURE, score_key=key)
        assert data.score == [float(s.scores["shape"].value[key]) for s in log.samples]
        assert all(rule.value_key == key and rule.config_hash for rule in data.scoring)
    with pytest.raises(ValueError, match="--score-key"):
        load_inspect_log(FIXTURE)
    with pytest.raises(ValueError, match="no named value"):
        load_inspect_log(FIXTURE, score_key="LENGTH")
    with pytest.raises(ValueError, match="nonempty"):
        load_inspect_log(FIXTURE, score_key="")
    with pytest.raises(ValueError, match="not dictionary-valued"):
        load_inspect_log(FIXTURE.with_name("inspect_tiny_qa.eval"), score_key="length")


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), "unknown"])
def test_bad_selected_value_never_becomes_zero_or_a_dropped_question(tmp_path, value):
    def mutate(log):
        log.samples[-1].scores["shape"].value["length"] = value
    with pytest.raises(ValueError, match="q3.*(unsupported|scalar)"):
        load_inspect_log(change(tmp_path, mutate), score_key="length")


def test_missing_or_scalar_row_refuses_the_whole_import(tmp_path):
    for mutation in (lambda s: s.value.pop("length"), lambda s: setattr(s, "value", 1)):
        path = change(tmp_path, lambda log, mutation=mutation: mutation(log.samples[-1].scores["shape"]))
        with pytest.raises(ValueError, match="q3"):
            load_inspect_log(path, score_key="length")


def test_literal_keys_and_unselected_values_do_not_change_the_selected_grade(tmp_path):
    key = 'grade/a.~[b] "quoted"'
    def mutate(log):
        for s in log.samples:
            s.scores["shape"].value[key] = 7
            s.scores["shape"].value["unselected"] = None
    data = load_inspect_log(change(tmp_path, mutate), score_key=key)
    assert data.score == [7, 7, 7]
    assert all(rule.value_key == key and rule.config_hash is None for rule in data.scoring)
    write_csv(data, tmp_path / "canonical.csv")
    assert load_csv(tmp_path / "canonical.csv").scoring == data.scoring


def test_selection_identity_blocks_native_and_roundtrip_pairing_even_with_unknown_parameters(tmp_path):
    for unknown in (False, True):
        a = load_inspect_log(FIXTURE, score_key="length")
        b = load_inspect_log(FIXTURE, score_key="has_digit")
        a.model = ["A"] * len(a)
        b.model = ["B"] * len(b)
        if unknown:
            for data in (a, b):
                data.scoring = [ScoringRule(rule.name, None, rule.value_key) for rule in data.scoring]
        combined = concat([("a", a), ("b", b)])
        write_csv(combined, tmp_path / "canonical.csv")
        for data in (combined, load_csv(tmp_path / "canonical.csv")):
            review = review_comparison(data, "A", "B")
            assert review.comparison is None and review.cohort["n_scoring_conflicting"] == 3
            assert {r["scorer_value"] for r in review.as_dict()["score_values"]} == {"length", "has_digit"}
            with pytest.raises(ValueError, match="conflicting scoring rules"):
                build_leaderboard(data)


def test_selected_result_parameters_cannot_be_borrowed_from_another_value(tmp_path):
    def mutate(log):
        log.results.scores = [s for s in log.results.scores if s.name != "length"]
    rule = load_inspect_log(change(tmp_path, mutate), score_key="length").scoring[0]
    assert rule.value_key == "length" and rule.config_hash is None


def test_cli_import_summary_comparison_and_leaderboard_retain_selection(tmp_path):
    specs = [f"A={FIXTURE}", f"B={FIXTURE}"]
    for command in ("compare", "leaderboard"):
        result = run_cli(command, *specs, "--score-key", "length", "--json")
        assert result.returncode == 0, result.stderr
        assert {r["scorer_value"] for r in json.loads(result.stdout)["score_values"]} == {"length"}
    result = run_cli("summarize", str(FIXTURE), "--score-key", "length", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["mean"] == 33
    output = tmp_path / "canonical.csv"
    imported = run_cli("import", "inspect", str(FIXTURE), "--score-key", "length", "-o", str(output))
    assert imported.returncode == 0, imported.stderr
    assert load_csv(output).scoring[0].value_key == "length"
    with pytest.raises(ValueError, match="no Inspect log"):
        load_inputs([output], score_key="length")


def test_canonical_value_metadata_validates_and_respects_column_mapping(tmp_path):
    path = tmp_path / "data.jsonl"
    row = {"question_id": "q", "model": "a", "score": 1, "scorer": "custom", "dimension": "correct"}
    path.write_text(json.dumps(row) + "\n")
    assert load_jsonl(path, ColumnMap(scorer_value="dimension")).scoring[0].value_key == "correct"
    for value in ([], 1, " "):
        row["dimension"] = value
        path.write_text(json.dumps(row) + "\n")
        with pytest.raises(ValueError, match="scorer_value"):
            load_jsonl(path, ColumnMap(scorer_value="dimension"))
    row["dimension"] = "correct"
    row.pop("scorer")
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="requires a scorer"):
        load_jsonl(path, ColumnMap(scorer_value="dimension"))
    with pytest.raises(ValueError, match="scorer_value"):
        EvalData(["q"], ["a"], [1], scoring=[ScoringRule("custom", None, " ")]).validate()
