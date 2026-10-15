"""Recorded generation-metric kwargs must not disappear before paired inference."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from scipy.stats import binomtest

from errorbars.adapters.lm_eval import load_lm_eval_samples, model_metadata_path
from errorbars.inputs import load_inputs
from errorbars.io import concat, load_csv, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import write_comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "studies/lm-eval-grading/captures"


def pair(other: str):
    return load_inputs([f"A={CAPTURES / 'strict'}", f"B={CAPTURES / other}"]).data


def modified(tmp_path, change):
    samples = next((CAPTURES / "strict").rglob("samples_*.jsonl"))
    destination = tmp_path / samples.name
    shutil.copyfile(samples, destination)
    metadata_path = model_metadata_path(samples)
    metadata = json.loads(metadata_path.read_text())
    change(metadata)
    model_metadata_path(destination).write_text(json.dumps(metadata))
    return destination


def test_native_unchanged_answers_with_changed_case_rule_cannot_be_a_model_improvement(tmp_path):
    records = []
    for label in ("strict", "folded"):
        path = next((CAPTURES / label).rglob("samples_*.jsonl"))
        records.append([json.loads(line) for line in path.read_text().splitlines()])
    assert [(r["doc"], r["target"], r["resps"]) for r in records[0]] == [
        (r["doc"], r["target"], r["resps"]) for r in records[1]
    ]
    data = pair("folded")
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_identity_matching"] == 24
    assert review.cohort["n_scoring_conflicting"] == 24
    assert review.comparison is review.inference is None
    assert review.cohort["mean_difference"] is None
    assert all(q.difference is None and q.presence == "conflicting" for q in review.questions)
    with pytest.raises(ValueError, match="conflicting scoring rules"):
        build_leaderboard(data)
    path = tmp_path / "canonical.csv"
    write_csv(data, path)
    restored = load_csv(path)
    assert restored.scoring == data.scoring
    assert review_comparison(restored, "A", "B").comparison is None
    with pytest.raises(ValueError, match="conflicting scoring rules"):
        build_leaderboard(restored)


@pytest.mark.parametrize("label,delta,discordant", [
    ("strict-repeat", 0, 0), ("prompt-variant", 0, 0), ("improved-strict", -1/3, 8),
])
def test_common_grader_controls_keep_independent_exact_inference(label, delta, discordant):
    data = pair(label)
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_scoring_matching"] == 24
    assert review.cohort["n_scoring_conflicting"] == 0
    assert review.comparison.mean_diff == pytest.approx(delta)
    assert review.inference.p_value == (binomtest(0, discordant).pvalue if discordant else 1.)
    assert len(build_leaderboard(data).entries) == 2


def test_unrelated_task_and_model_settings_do_not_change_selected_grading_definition(tmp_path):
    def change(metadata):
        config = metadata["configs"]["grading_contract"]
        config.update(num_fewshot=12, description="A different prompt instruction")
        config["generation_kwargs"] = {"temperature": 0.7}
        config["metric_list"].append({"metric": "another_metric", "ignore_case": True})
        metadata["model_name"] = "different-model"

    path = modified(tmp_path, change)
    assert load_lm_eval_samples(path).scoring == pair("strict-repeat").scoring[:24]


def test_private_grader_values_are_hashed_without_execution_or_export(tmp_path):
    marker = "PRIVATE_GRADING_PATTERN_NOT_FOR_THE_REPORT"
    canary = tmp_path / "must-not-be-created"

    def change(metadata):
        declaration = metadata["configs"]["grading_contract"]["metric_list"][0]
        declaration["regexes_to_ignore"] = [marker, f"__import__('pathlib').Path({str(canary)!r}).touch()"]

    path = modified(tmp_path, change)
    data = load_lm_eval_samples(path)
    assert all(rule.config_hash.startswith("lm-eval-generation-params-v1:") for rule in data.scoring)
    data.model = ["B"] * len(data)
    combined = concat([("A", pair("strict-repeat").filter_model("A")), ("B", data)])
    review = review_comparison(combined, "A", "B")
    assert review.cohort["n_scoring_conflicting"] == 24
    assert marker not in json.dumps(review.as_dict())
    csv_path, html_path = tmp_path / "export.csv", tmp_path / "report.html"
    write_csv(combined, csv_path)
    write_comparison_html(review, html_path)
    assert marker not in csv_path.read_text() and marker not in html_path.read_text()
    assert not canary.exists()


@pytest.mark.parametrize("remove", ["configs", "metric_list", "selected_metric", "output_type"])
def test_missing_applicable_declaration_stays_unknown(tmp_path, remove):
    def change(metadata):
        if remove == "configs":
            metadata.pop("configs")
        else:
            config = metadata["configs"]["grading_contract"]
            if remove == "selected_metric":
                config["metric_list"] = [{"metric": "unrelated"}]
            else:
                config.pop(remove)

    data = load_lm_eval_samples(modified(tmp_path, change))
    assert all(rule.config_hash is None for rule in data.scoring)


def test_unused_kwargs_cannot_certify_custom_processors_or_other_output_types(tmp_path):
    def custom(metadata):
        metadata["configs"]["grading_contract"]["process_results"] = "def custom(doc, results): ..."

    data = load_lm_eval_samples(modified(tmp_path, custom))
    assert all(rule.config_hash is None for rule in data.scoring)
    # The pre-existing real custom-processor study remains usable under an explicit common metric.
    previous = ROOT / "studies/lm-eval-evidence/captures"
    custom_data = load_inputs([f"A={previous / 'exact-first'}", f"B={previous / 'casefold-first'}"],
                              metric="exact").data
    review = review_comparison(custom_data, "A", "B")
    assert review.cohort["n_scoring_unavailable"] == 24
    assert review.comparison.mean_diff == 0
    assert review.inference.p_value == 1


@pytest.mark.parametrize("output_type", ["multiple_choice", "loglikelihood", "loglikelihood_rolling"])
def test_other_output_branches_do_not_certify_unused_generation_kwargs(tmp_path, output_type):
    def change(metadata):
        metadata["configs"]["grading_contract"]["output_type"] = output_type

    data = load_lm_eval_samples(modified(tmp_path, change))
    assert all(rule.config_hash is None for rule in data.scoring)


def test_nonfinite_recorded_grading_parameters_are_rejected(tmp_path):
    def change(metadata):
        metadata["configs"]["grading_contract"]["metric_list"][0]["regexes_to_ignore"] = [float("nan")]

    with pytest.raises(ValueError, match="invalid recorded grading parameters"):
        load_lm_eval_samples(modified(tmp_path, change))


@pytest.mark.parametrize("value", [1, "false", None, []])
def test_malformed_backend_declaration_does_not_become_a_matching_fingerprint(tmp_path, value):
    def change(metadata):
        metadata["configs"]["grading_contract"]["metric_list"][0]["hf_evaluate"] = value

    with pytest.raises(ValueError, match="hf_evaluate must be a boolean"):
        load_lm_eval_samples(modified(tmp_path, change))


def test_different_backend_and_conflicting_duplicate_kwargs_are_retained(tmp_path):
    def change(metadata):
        metadata["configs"]["grading_contract"]["metric_list"][0]["hf_evaluate"] = True

    data = load_lm_eval_samples(modified(tmp_path, change))
    assert data.scoring != pair("strict-repeat").scoring[:24]

    def duplicate(metadata):
        declarations = metadata["configs"]["grading_contract"]["metric_list"]
        declarations.append({**declarations[0], "ignore_case": True})

    with pytest.raises(ValueError, match="conflicting recorded grading parameters"):
        load_lm_eval_samples(modified(tmp_path, duplicate))
