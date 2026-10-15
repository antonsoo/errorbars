"""Native scalar values need compatible aggregation and an honest rank direction."""

from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

import pytest
from scipy.stats import ttest_rel

from errorbars.adapters.lm_eval import load_lm_eval_samples, model_metadata_path
from errorbars.inputs import load_inputs
from errorbars.io import ColumnMap, EvalData, concat, load_csv, load_dataframe, load_jsonl, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.plot import forest_plot_matplotlib, forest_plot_svg
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "studies/metric-contract/captures"


def native(metric: str = "mean_nll") -> EvalData:
    return load_inputs([CAPTURES / "precise", CAPTURES / "noisy"], metric=metric).data


def modified_metadata(tmp_path: Path, change) -> Path:
    source = next((CAPTURES / "precise").rglob("samples_*.jsonl"))
    samples = tmp_path / source.name
    shutil.copyfile(source, samples)
    sidecar = model_metadata_path(source)
    assert sidecar is not None
    metadata = json.loads(sidecar.read_text())
    change(metadata)
    destination = model_metadata_path(samples)
    assert destination is not None
    destination.write_text(json.dumps(metadata))
    return samples


@pytest.mark.parametrize("metric,direction", [("mean_nll", False), ("likelihood", True)])
def test_native_harness_metric_order_and_values_match_recorded_results(metric, direction):
    data = native(metric)
    board = build_leaderboard(data)
    assert board.higher_is_better is direction and board.direction_source == "recorded"
    assert [entry.model for entry in board.entries] == ["precise", "noisy"]
    assert set(data.higher_is_better) == {direction}
    for entry in board.entries:
        sidecar = next((CAPTURES / entry.model).rglob("results_*.json"))
        expected = json.loads(sidecar.read_text())["results"]["metric_contract"][metric + ",none"]
        assert entry.mean == pytest.approx(expected)
    paired = board.pairwise[0]
    a, b = (data.filter_model(model).score for model in (paired.model_a, paired.model_b))
    assert paired.p_value_used == pytest.approx(ttest_rel(a, b).pvalue, rel=1e-10)
    assert paired.comparison.mean_diff == pytest.approx(sum(a) / len(a) - sum(b) / len(b))
    assert (paired.comparison.mean_diff > 0) is direction


def test_declaring_rank_direction_does_not_negate_data_or_change_two_sided_inference():
    data = native()
    original = list(data.score)
    low = build_leaderboard(data)
    data.higher_is_better = None
    high = build_leaderboard(data)
    explicit = build_leaderboard(data, higher_is_better=False)
    assert [e.model for e in high.entries] == ["noisy", "precise"]
    assert low.entries == explicit.entries
    assert data.score == original
    assert low.pairwise[0].p_value_used == pytest.approx(high.pairwise[0].p_value_used)
    assert low.pairwise[0].comparison.mean_diff == -high.pairwise[0].comparison.mean_diff
    assert explicit.direction_source == "explicit" and high.direction_source == "default"


def test_direction_survives_filter_concat_csv_jsonl_dataframe_and_question_report(tmp_path):
    data = native()
    csv_path = tmp_path / "native.csv"
    write_csv(data, csv_path)
    restored = load_csv(csv_path)
    assert restored.higher_is_better == data.higher_is_better
    rows = [
        {"question_id": q, "model": m, "score": s, "direction": d}
        for q, m, s, d in zip(data.question_id, data.model, data.score, data.higher_is_better, strict=True)
    ]
    jsonl = tmp_path / "native.jsonl"
    jsonl.write_text("\n".join(json.dumps(row) for row in rows))
    from_json = load_jsonl(jsonl, ColumnMap(higher_is_better="direction"))
    pd = pytest.importorskip("pandas")
    from_df = load_dataframe(pd.DataFrame(rows), ColumnMap(higher_is_better="direction"))
    for roundtrip in (restored, from_json, from_df):
        assert roundtrip.higher_is_better == data.higher_is_better
        combined = concat([(model, roundtrip.filter_model(model)) for model in data.models()])
        assert build_leaderboard(combined).entries == build_leaderboard(data).entries
        review = review_comparison(combined, "precise", "noisy").as_dict()
        assert all(obs["higher_is_better"] is False for q in review["questions"]
                   for obs in q["observations_a"] + q["observations_b"])


def test_unknown_directions_remain_unknown_when_combined_with_recorded_data(tmp_path):
    a, b = (native().filter_model(model) for model in ("precise", "noisy"))
    b.higher_is_better = None
    combined = concat([("a", a), ("b", b)])
    path = tmp_path / "mixed.csv"
    write_csv(combined, path)
    restored = load_csv(path)
    assert restored.higher_is_better == [False] * 32 + [None] * 32
    board = build_leaderboard(restored)
    assert not board.higher_is_better
    assert any("unrecorded for 32 observations" in note for note in board.warnings)
    explicit = build_leaderboard(restored, higher_is_better=False)
    assert explicit.direction_source == "explicit"


@pytest.mark.parametrize("direction", [True, False, None])
def test_contradictory_native_directions_cannot_be_overridden(direction):
    data = native()
    data.higher_is_better[32:] = [True] * 32
    with pytest.raises(ValueError, match="conflicting score directions"):
        build_leaderboard(data, higher_is_better=direction)


def test_recorded_direction_cannot_be_overridden_and_repeated_questions_cannot_disagree():
    with pytest.raises(ValueError, match="conflicts with recorded"):
        build_leaderboard(native(), higher_is_better=True)
    data = EvalData(["q", "q"], ["m", "m"], [0, 1], sample=["1", "2"],
                    higher_is_better=[False, True])
    with pytest.raises(ValueError, match="conflicting score directions"):
        data.scores_by_question()


@pytest.mark.parametrize("value", [0, 1, "no", "0", {}, [], 0.0])
def test_malformed_normalized_direction_is_not_silently_dropped(tmp_path, value):
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps({"question_id": "q", "model": "m", "score": 0,
                                "higher_is_better": value}))
    with pytest.raises(ValueError, match="higher_is_better must be"):
        load_jsonl(path)


@pytest.mark.parametrize("value", [0, 1, "false", [], {}])
def test_malformed_direct_library_direction_is_not_truthiness_coerced(value):
    data = EvalData(["q"], ["m"], [0], higher_is_better=[value])
    with pytest.raises(ValueError, match="higher_is_better must be"):
        data.validate()
    with pytest.raises(ValueError, match="higher_is_better must be"):
        build_leaderboard(native(), higher_is_better=value)


def test_native_non_mean_metric_inputs_cannot_be_reported_as_that_metric():
    with pytest.raises(ValueError, match="not an arithmetic mean"):
        native("perplexity")


@pytest.mark.parametrize("aggregation", ["median", "perplexity", "weighted_perplexity", "nanmean"])
def test_non_mean_aggregation_declarations_are_refused_even_on_scalars(tmp_path, aggregation):
    samples = modified_metadata(tmp_path, lambda m: m["configs"]["metric_contract"]["metric_list"][0].update(
        aggregation=aggregation))
    with pytest.raises(ValueError, match="not an arithmetic mean"):
        load_lm_eval_samples(samples, model="renamed", metric="mean_nll")


@pytest.mark.parametrize("value", [0, 1, "false", [], {}])
def test_malformed_native_direction_cannot_be_bypassed_with_an_explicit_model(tmp_path, value):
    samples = modified_metadata(
        tmp_path, lambda m: m["higher_is_better"]["metric_contract"].update(mean_nll=value),
    )
    with pytest.raises(ValueError, match="higher_is_better must be"):
        load_lm_eval_samples(samples, model="renamed", metric="mean_nll")


def test_result_and_task_direction_declarations_must_agree(tmp_path):
    samples = modified_metadata(
        tmp_path, lambda m: m["higher_is_better"]["metric_contract"].update(mean_nll=True),
    )
    with pytest.raises(ValueError, match="conflicting higher_is_better"):
        load_lm_eval_samples(samples, metric="mean_nll")


def test_missing_mean_aggregation_cannot_apply_an_aggregate_direction_to_unknown_inputs(tmp_path):
    samples = modified_metadata(tmp_path, lambda m: m.pop("configs"))
    with pytest.raises(ValueError, match="no recorded mean aggregation"):
        load_lm_eval_samples(samples, metric="mean_nll")
    assert load_lm_eval_samples(samples, metric="likelihood").higher_is_better == [True] * 32
    with pytest.raises(ValueError, match="no recorded mean aggregation"):
        load_lm_eval_samples(samples, metric="perplexity")


def test_missing_directions_are_not_inferred_from_metric_names_or_scores(tmp_path):
    def remove(metadata):
        metadata.pop("higher_is_better")
        metadata["configs"]["metric_contract"]["metric_list"][0].pop("higher_is_better")

    samples = modified_metadata(tmp_path, remove)
    assert load_lm_eval_samples(samples, metric="mean_nll").higher_is_better is None


@pytest.mark.parametrize("left,right", list(itertools.permutations([True, False, None], 2)))
def test_csv_retains_false_and_unknown_without_assuming_that_false_is_absent(tmp_path, left, right):
    data = EvalData(["a", "b"], ["m", "m"], [0.2, 0.4], higher_is_better=[left, right])
    path = tmp_path / "directions.csv"
    write_csv(data, path)
    assert load_csv(path).higher_is_better == [left, right]


def test_both_forest_plot_formats_name_lower_first_order():
    board = build_leaderboard(native())
    assert "lower scores first (recorded)" in forest_plot_svg(board)
    fig = forest_plot_matplotlib(board)
    assert "lower scores first; recorded" in fig.axes[0].get_xlabel()
