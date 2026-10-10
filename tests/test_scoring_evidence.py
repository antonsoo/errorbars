"""An unchanged answer cannot become a model improvement by changing the grader."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest
from scipy.stats import binomtest
from test_cli import run_cli

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.adapters.lm_eval import load_lm_eval_samples
from errorbars.inputs import load_inputs
from errorbars.io import ColumnMap, EvalData, ScoringRule, concat, load_csv, load_jsonl, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "examples/inspect-scoring/logs"


def pair(other: str) -> EvalData:
    pytest.importorskip("inspect_ai")
    return load_inputs([f"A={LOGS / 'exact.eval'}", f"B={LOGS / (other + '.eval')}"]).data


@pytest.mark.parametrize("other", ["anywhere", "includes"])
def test_unchanged_native_responses_with_changed_grader_withhold_inference_and_ranking(tmp_path, other):
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    a, b = (read_eval_log(LOGS / f"{name}.eval") for name in ("exact", other))
    assert {s.id: s.output.completion for s in a.samples} == {s.id: s.output.completion for s in b.samples}
    data = pair(other)
    review = review_comparison(data, "A", "B")
    assert review.comparison is None and review.inference is None
    assert review.cohort["n_identity_matching"] == 24
    assert review.cohort["n_scoring_conflicting"] == 24
    assert review.cohort["mean_difference"] is None
    assert all(q.difference is None and q.presence == "conflicting" for q in review.questions)
    with pytest.raises(ValueError, match="conflicting scoring rules"):
        build_leaderboard(data)
    write_csv(data, tmp_path / "canonical.csv")
    restored = load_csv(tmp_path / "canonical.csv")
    assert restored.scoring == data.scoring
    assert review_comparison(restored, "A", "B").comparison is None
    with pytest.raises(ValueError, match="conflicting scoring rules"):
        build_leaderboard(restored)


@pytest.mark.parametrize("other,delta,discordant", [("exact-repeat", 0, 0), ("improved-exact", -1/3, 8)])
def test_common_grader_controls_agree_with_independent_exact_test(other, delta, discordant):
    review = review_comparison(pair(other), "A", "B")
    assert review.cohort["n_scoring_matching"] == 24
    assert review.comparison.mean_diff == pytest.approx(delta)
    expected = binomtest(0, discordant).pvalue if discordant else 1.0
    assert review.inference.p_value == expected
    assert len(build_leaderboard(pair(other)).entries) == 2


def test_cli_import_and_report_keep_changed_grader_evidence(tmp_path):
    pytest.importorskip("inspect_ai")
    specs = [f"A={LOGS / 'exact.eval'}", f"B={LOGS / 'anywhere.eval'}"]
    canonical = tmp_path / "canonical.csv"
    imported = run_cli("import", "inspect", *specs, "-o", str(canonical))
    assert imported.returncode == 0, imported.stderr
    for paths in (specs, [str(canonical)]):
        report = tmp_path / "conflict.html"
        result = run_cli("compare", *paths, "--html", str(report), "--json")
        assert result.returncode == 1 and not result.stdout
        assert "conflicting scoring rules" in result.stderr and "Traceback" not in result.stderr
        assert "Inference unavailable" in report.read_text()
        assert '"scorer":"inspect:match"' in report.read_text()
        ranked = run_cli("leaderboard", *paths, "--json")
        assert ranked.returncode == 1 and not ranked.stdout
        assert "conflicting scoring rules" in ranked.stderr


def test_native_rescoring_uses_result_parameters(tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai import score
    from inspect_ai.log import read_eval_log, write_eval_log
    from inspect_ai.scorer import match

    original = read_eval_log(LOGS / "exact.eval")
    rescored = score(original, match(location="any"), action="overwrite", display="none")
    path = tmp_path / "rescored.eval"
    write_eval_log(rescored, path)
    data = load_inspect_log(path)
    assert data.scoring == load_inspect_log(LOGS / "anywhere.eval").scoring
    assert data.scoring != load_inspect_log(LOGS / "exact.eval").scoring


def test_parameter_order_does_not_change_fingerprint_or_export_private_grader_text(tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log, write_eval_log

    marker = "PRIVATE_GRADER_PROMPT_MUST_STAY_IN_THE_NATIVE_LOG"
    definitions = []
    for i, params in enumerate((
        {"location": "exact", "template": marker, "nested": {"b": 2, "a": 1}},
        {"nested": {"a": 1, "b": 2}, "template": marker, "location": "exact"},
    )):
        log = read_eval_log(LOGS / "exact.eval")
        log.results.scores[0].params = params
        path = tmp_path / f"params-{i}.eval"
        write_eval_log(log, path)
        definitions.append(load_inspect_log(path))
    assert definitions[0].scoring == definitions[1].scoring
    definitions[0].model = ["A"] * 24
    definitions[1].model = ["B"] * 24
    data = concat([("a", definitions[0]), ("b", definitions[1])])
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_scoring_matching"] == 24
    assert marker not in json.dumps(review.as_dict())
    write_csv(data, tmp_path / "export.csv")
    assert marker not in (tmp_path / "export.csv").read_text()


def test_absent_json_parameter_field_is_unknown_not_an_empty_configuration(tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    log = read_eval_log(LOGS / "exact.eval").model_dump(mode="json")
    del log["results"]["scores"][0]["params"]
    path = tmp_path / "missing-params.json"
    path.write_text(json.dumps(log))
    data = load_inspect_log(path)
    assert all(rule.name == "inspect:match" and rule.config_hash is None for rule in data.scoring)


def test_missing_result_parameters_stay_unknown_and_conflicting_metadata_is_refused(tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log, write_eval_log

    log = read_eval_log(LOGS / "exact.eval")
    extra = log.results.scores[0].model_copy(deep=True)
    extra.reducer = "mean"
    log.results.scores.append(extra)
    path = tmp_path / "same.eval"
    write_eval_log(log, path)
    assert load_inspect_log(path).scoring == load_inspect_log(LOGS / "exact.eval").scoring
    extra.params = {"location": "any"}
    write_eval_log(log, path)
    with pytest.raises(ValueError, match="conflicting recorded parameters"):
        load_inspect_log(path)
    log.results.scores.clear()
    write_eval_log(log, path)
    unknown = load_inspect_log(path)
    assert all(rule.name == "inspect:match" and rule.config_hash is None for rule in unknown.scoring)
    unknown.model = ["B"] * len(unknown)
    a = load_inspect_log(LOGS / "exact.eval")
    a.model = ["A"] * len(a)
    review = review_comparison(concat([("a", a), ("b", unknown)]), "A", "B")
    assert review.comparison is not None
    assert review.cohort["n_scoring_unavailable"] == 24
    assert review.cohort["n_scoring_matching"] == 0


@pytest.mark.parametrize("rules", list(itertools.permutations([
    ScoringRule("match", "exact"), ScoringRule("match", "any"), None,
])))
def test_an_unknown_repeat_cannot_erase_a_known_conflicting_configuration(rules):
    data = EvalData(["q"] * 3, ["A"] * 3, [0, 1, 1], sample=["1", "2", "3"], scoring=list(rules))
    with pytest.raises(ValueError, match="conflicting scoring rules across samples"):
        data.scores_by_question()


def test_normalized_jsonl_mapping_preserves_partial_scoring_and_source_privacy(tmp_path):
    rows = [
        {"question_id": q, "model": model, "score": score, "rule": rule, "config": config}
        for q, model, score, rule, config in [
            ("q1", "A", 0, "accuracy", None), ("q1", "B", 1, "safety", None),
            ("q2", "A", 0, "accuracy", "v1"), ("q2", "B", 1, None, None),
        ]
    ]
    path = tmp_path / "scores.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    data = load_jsonl(path, ColumnMap(scorer="rule", scorer_config="config"))
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_scoring_conflicting"] == 1
    assert review.cohort["n_scoring_unavailable"] == 1
    assert review.comparison is None
    assert review.questions[0].observations_a[0].scorer == "accuracy"
    assert review.questions[1].difference == -1
    assert str(tmp_path) not in json.dumps(review.as_dict())


def test_lm_eval_declared_metric_survives_separate_normalized_exports(tmp_path):
    path = ROOT / "tests/fixtures/samples_arc_easy_2026-09-24T03-05-32.831346.jsonl"
    parts = []
    for model, metric in (("A", "acc"), ("B", "acc_norm")):
        data = load_lm_eval_samples(path, model=model, metric=metric)
        target = tmp_path / f"{model}.csv"
        write_csv(data, target)
        parts.append(str(target))
    data = load_inputs(parts).data
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_scoring_conflicting"] == 5
    assert review.comparison is None


@pytest.mark.parametrize("scorer,config", [(None, "v1"), (3, None), ("match", 3), (" ", None)])
def test_malformed_normalized_scoring_is_not_silently_dropped(tmp_path, scorer, config):
    path = tmp_path / "scores.jsonl"
    path.write_text(json.dumps({"question_id": "q", "model": "A", "score": 1,
                                "scorer": scorer, "scorer_config": config}))
    with pytest.raises(ValueError, match="scorer"):
        load_jsonl(path)
