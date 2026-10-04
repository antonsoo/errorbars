"""Counterexamples to draw weighting, ambiguous input and invalid paired inference."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as sp_stats
from statsmodels.api import OLS
from test_cli import run_cli

from errorbars.compare import mcnemar_exact, paired_compare
from errorbars.io import EvalData, concat, load_csv, load_jsonl
from errorbars.leaderboard import build_leaderboard
from errorbars.stats import (
    bootstrap_ci,
    cluster_robust_se,
    intraclass_correlation,
    is_binary,
    mean_ci_clt,
    within_between_variance,
)


def repeated_data() -> EvalData:
    return EvalData(
        ["q1"] * 10 + ["q2", "q1", "q2"],
        ["a"] * 11 + ["b"] * 2,
        [1.0] * 10 + [0.0, 0.7, 0.7],
        sample=[str(i) for i in range(10)] + ["0"] * 3,
    )


def test_repeated_leaderboard_matches_question_mean_oracle() -> None:
    board = build_leaderboard(repeated_data())
    assert [entry.model for entry in board.entries] == ["b", "a"]
    a = next(entry for entry in board.entries if entry.model == "a")
    assert a.mean == 0.5
    assert a.n == 2
    assert a.n_observations == 11
    assert a.method == "clt"
    assert a.se == pytest.approx(np.std([1.0, 0.0], ddof=1) / np.sqrt(2))
    assert a.ci_high == pytest.approx(0.5 + sp_stats.norm.ppf(0.975) * a.se)


@pytest.mark.parametrize("method", ["auto", "clt", "bootstrap"])
def test_repeated_summary_uses_questions_and_preserves_counts(tmp_path: Path, method: str) -> None:
    from errorbars.io import write_csv

    path = tmp_path / "repeat.csv"
    write_csv(repeated_data().filter_model("a"), path)
    result = run_cli("summarize", str(path), "--ci", method, "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mean"] == 0.5
    assert report["n"] == report["n_questions"] == 2
    assert report["n_observations"] == 11
    assert report["analysis_unit"] == "question"
    assert "within_between" in report
    if method != "bootstrap":
        assert report["se"] == pytest.approx(0.5)


def test_repeated_wilson_is_not_a_binomial_trial_count(tmp_path: Path) -> None:
    path = tmp_path / "repeat.csv"
    path.write_text("question_id,model,score,sample\nq1,a,1,0\nq1,a,1,1\nq2,a,0,0\n")
    result = run_cli("summarize", str(path), "--ci", "wilson", "--json")
    assert result.returncode != 0
    assert "repeated" in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("lift", [1.0, -1.0])
def test_constant_nonzero_difference_matches_scipy_limit(lift: float) -> None:
    a, b = [lift] * 8, [0.0] * 8
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        expected = sp_stats.ttest_rel(a, b)
    ours = paired_compare(a, b)
    assert ours.p_value == expected.pvalue == 0.0
    assert ours.se_paired == 0.0
    assert ours.ci_low == ours.ci_high == lift
    assert any("zero" in note for note in ours.warnings)


@pytest.mark.parametrize(
    "a,b",
    [
        ([[1, 0], [0, 1]], [[0, 1], [1, 0]]),
        ([1, float("nan")], [0, 1]),
        ([1, float("inf")], [0, 1]),
        ([1e308, 0], [0, 1]),
    ],
)
def test_paired_rejects_invalid_score_vectors(a, b) -> None:
    with pytest.raises(ValueError):
        paired_compare(a, b)


@pytest.mark.parametrize(
    "a,b", [([1, 0, 1], [0]), ([0.999999, 0], [0, 1]), ([[1, 0]], [[0, 1]]), ([float("nan")], [0])]
)
def test_mcnemar_cannot_broadcast_or_guess_binary(a, b) -> None:
    with pytest.raises(ValueError):
        mcnemar_exact(a, b)


def test_nearly_binary_scores_remain_continuous() -> None:
    assert not is_binary([0.999999, 0.000001])
    assert paired_compare([0.999999, 0.5], [0, 1]).mcnemar is None


@pytest.mark.parametrize(
    "groups", [["only"] * 4, ["a", "b"], [["a", "a"], ["b", "b"]], ["a", "b", None, "b"]]
)
def test_clustered_se_rejects_missing_or_invalid_independent_groups(groups) -> None:
    with pytest.raises(ValueError):
        cluster_robust_se([0.1, 0.3, 0.7, 0.8], groups)


def test_question_mean_clustered_interval_matches_independent_ols(tmp_path: Path) -> None:
    # Unequal draws per question, then unequal questions per passage.
    path = tmp_path / "clustered.csv"
    lines = ["question_id,model,score,sample,cluster_id"]
    scores = [0.1, 0.3, 0.4, 0.9, 0.8, 0.7]
    clusters = ["x", "x", "y", "z", "z", "z"]
    for q, (score, cluster) in enumerate(zip(scores, clusters, strict=True)):
        for sample in range(q + 1):
            lines.append(f"q{q},a,{score},{sample},{cluster}")
    path.write_text("\n".join(lines) + "\n")
    result = run_cli("summarize", str(path), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    oracle = OLS(scores, np.ones((6, 1))).fit(cov_type="cluster", cov_kwds={"groups": clusters})
    expected_se = oracle.bse[0]
    assert report["mean"] == pytest.approx(np.mean(scores))
    assert report["clustered"]["clustered_se"] == pytest.approx(expected_se)
    assert report["clustered"]["clustered_ci_high"] == pytest.approx(
        np.mean(scores) + sp_stats.t.ppf(0.975, 2) * expected_se
    )


def test_conflicting_cluster_assignments_are_not_first_row_wins() -> None:
    data = EvalData(
        ["q1", "q2", "q1", "q2"],
        ["a", "a", "b", "b"],
        [1, 0, 0, 1],
        cluster_id=["p1", "p2", "wrong", "wrong"],
    )
    with pytest.raises(ValueError, match="conflicting cluster"):
        data.cluster_by_question()


def test_clusters_from_one_source_apply_to_shared_unlabelled_questions() -> None:
    a = EvalData(["q1", "q2"], ["a", "a"], [1, 0])
    b = EvalData(["q1", "q2"], ["b", "b"], [0, 1], cluster_id=["p1", "p2"])
    assert concat([("a.csv", a), ("b.csv", b)]).cluster_id == ["p1", "p2", "p1", "p2"]
    c = EvalData(["unlabelled"], ["c"], [1])
    with pytest.raises(ValueError, match="cluster assignment"):
        concat([("c.csv", c), ("b.csv", b)])


@pytest.mark.parametrize("header", ["question_id,model,score,score", "question_id,model,score, score "])
def test_duplicate_normalized_csv_headers_are_rejected(tmp_path: Path, header: str) -> None:
    path = tmp_path / "scores.csv"
    path.write_text(header + "\nq1,a,1,0\n")
    with pytest.raises(ValueError, match="duplicate.*score"):
        load_csv(path)


@pytest.mark.parametrize("field", ["question_id", "model", "cluster_id", "sample"])
@pytest.mark.parametrize("value", [None, "", {"a": 1}, ["a"]])
def test_invalid_identifiers_cannot_become_fake_labels(tmp_path: Path, field: str, value) -> None:
    row = {"question_id": "q1", "model": "a", "score": 1, field: value}
    path = tmp_path / "scores.jsonl"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match=field):
        load_jsonl(path)


def test_duplicate_json_score_keys_are_not_last_field_wins(tmp_path: Path) -> None:
    path = tmp_path / "scores.jsonl"
    path.write_text('{"question_id":"q1","model":"a","score":1,"score":0}\n')
    with pytest.raises(ValueError, match="duplicate.*score"):
        load_jsonl(path)


@pytest.mark.parametrize("values", [[[1, 0], [0, 1]], [1, float("nan")], [0, float("inf")]])
def test_mean_intervals_cannot_emit_nonfinite_or_flattened_results(values) -> None:
    with pytest.raises(ValueError):
        mean_ci_clt(values)


@pytest.mark.parametrize("scale", [1e-200, 1e-100, 1.0, 1e100])
def test_units_do_not_turn_nonconstant_differences_into_zero_variance(scale: float) -> None:
    # SciPy itself underflows on the raw tiny units; compare against its rescaled oracle.
    a, b = np.array([1.0, 2.0, 4.0, 8.0]), np.array([0.0, 1.0, 1.0, 3.0])
    oracle = sp_stats.ttest_rel(a, b)
    comp = paired_compare(a * scale, b * scale)
    assert comp.p_value == pytest.approx(oracle.pvalue, rel=1e-10)
    assert comp.se_paired / scale == pytest.approx(np.std(a - b, ddof=1) / 2)
    assert comp.correlation == pytest.approx(sp_stats.pearsonr(a, b).statistic)
    assert comp.se_unpaired / scale == pytest.approx(np.hypot(np.std(a, ddof=1), np.std(b, ddof=1)) / 2)
    assert not comp.warnings
    mean = mean_ci_clt(a * scale)
    assert mean.se / scale == pytest.approx(np.std(a, ddof=1) / 2)
    cluster_oracle = OLS(a, np.ones((4, 1))).fit(cov_type="cluster", cov_kwds={"groups": [0, 0, 1, 1]})
    assert cluster_robust_se(a * scale, [0, 0, 1, 1]) / scale == pytest.approx(cluster_oracle.bse[0])


def test_zero_difference_convention_is_visible_and_exact_binary_is_retained() -> None:
    comp = paired_compare([0, 1, 0, 1], [0, 1, 0, 1])
    assert comp.p_value == 1.0
    assert comp.warnings
    assert comp.mcnemar is not None and comp.mcnemar.p_value == 1.0


@pytest.mark.parametrize("command", ["summarize", "compare", "leaderboard"])
def test_single_passage_is_not_reinterpreted_as_independent_questions(tmp_path: Path, command: str) -> None:
    path = tmp_path / "single.csv"
    path.write_text("question_id,model,score,cluster_id\nq1,a,1,p\nq2,a,0,p\nq1,b,0,p\nq2,b,1,p\n")
    args = ["--model", "a"] if command == "summarize" else []
    result = run_cli(command, str(path), "--json", *args)
    assert result.returncode != 0
    assert "at least 2 independent clusters" in result.stderr
    assert "Traceback" not in result.stderr and not result.stdout


def test_conflicting_source_metadata_reports_both_sources() -> None:
    a = EvalData(["q1"], ["a"], [1], cluster_id=["p1"])
    b = EvalData(["q1"], ["b"], [0], cluster_id=["p2"])
    with pytest.raises(ValueError, match=r"b.csv:.*conflicting cluster.*a.csv"):
        concat([("a.csv", a), ("b.csv", b)])


def test_infile_clusters_resolve_shared_questions_without_filling_unknowns(tmp_path: Path) -> None:
    path = tmp_path / "scores.jsonl"
    rows = [
        {"question_id": "q1", "model": "a", "score": 1},
        {"question_id": "q1", "model": "b", "score": 0, "cluster_id": "p1"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows))
    assert load_jsonl(path).cluster_id == ["p1", "p1"]
    rows.append({"question_id": "q2", "model": "a", "score": 0})
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match=r"row 3: no cluster assignment.*q2"):
        load_jsonl(path)


def test_cluster_conflict_keeps_original_row_number(tmp_path: Path) -> None:
    path = tmp_path / "scores.csv"
    path.write_text("question_id,model,score,cluster_id\nq1,a,1,p1\nq1,b,0,p2\n")
    with pytest.raises(ValueError, match=r"row 2:.*conflicting cluster"):
        load_csv(path)


def test_harness_json_cannot_silently_overwrite_a_grade(tmp_path: Path) -> None:
    from errorbars.adapters.lm_eval import load_lm_eval_samples

    path = tmp_path / "samples_task_2026-10-04T12-00-00.jsonl"
    path.write_text('{"doc_id":0,"metrics":["acc"],"acc":1,"acc":0}\n')
    with pytest.raises(ValueError, match=r":1:.*duplicate.*acc"):
        load_lm_eval_samples(path, model="a")


def test_normalized_rows_cannot_accept_numeric_strings_then_crash_when_averaged() -> None:
    data = EvalData(["q1", "q2"], ["a", "a"], ["1", "0"])
    with pytest.raises(ValueError, match="normalized score must be numeric"):
        data.scores_by_question()


def test_sampled_binary_comparison_and_generation_counts_stay_distinct(tmp_path: Path) -> None:
    path = tmp_path / "repeat.csv"
    from errorbars.io import write_csv

    write_csv(repeated_data(), path)
    result = run_cli("compare", str(path), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mean_a"] == 0.5
    assert report["mean_b"] == 0.7
    assert report["n"] == 2
    assert report["n_observations_a"] == 11
    assert report["n_observations_b"] == 2


def test_equal_repeats_do_not_artificially_shrink_question_se(tmp_path: Path) -> None:
    path = tmp_path / "repeat.csv"
    lines = ["question_id,model,score,sample"]
    for question, score in enumerate([1, 0, 1, 0]):
        for sample in range(25):
            lines.append(f"q{question},a,{score},{sample}")
    path.write_text("\n".join(lines))
    result = run_cli("summarize", str(path), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["se"] == pytest.approx(np.std([1, 0, 1, 0], ddof=1) / 2)
    assert report["n"] == 4 and report["n_observations"] == 100


@pytest.mark.parametrize("value", [None, "pending", "", "nan", "inf"])
def test_inspect_cannot_turn_an_unknown_grade_into_zero(monkeypatch, value) -> None:
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    from errorbars.adapters.inspect_ai import load_inspect_log

    path = Path(__file__).parent / "fixtures" / "inspect_tiny_qa.eval"
    log = read_eval_log(str(path))
    log.samples[0].scores["match"].value = value
    monkeypatch.setattr("inspect_ai.log.read_eval_log", lambda _: log)
    with pytest.raises(ValueError, match="sample.*(grade|finite)"):
        load_inspect_log(path)


def test_inspect_cannot_drop_an_unscored_sample(monkeypatch) -> None:
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    from errorbars.adapters.inspect_ai import load_inspect_log

    path = Path(__file__).parent / "fixtures" / "inspect_tiny_qa.eval"
    log = read_eval_log(str(path))
    log.samples[0].scores = None
    monkeypatch.setattr("inspect_ai.log.read_eval_log", lambda _: log)
    with pytest.raises(ValueError, match="sample.*no scored"):
        load_inspect_log(path)


@pytest.mark.parametrize(
    "value,expected",
    [("C", 1), ("I", 0), ("P", 0.5), ("N", 0), ("true", 1), ("False", 0), ("0.25", 0.25), (True, 1)],
)
def test_recognized_inspect_grades_keep_vendor_conversion(monkeypatch, value, expected) -> None:
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    from errorbars.adapters.inspect_ai import load_inspect_log

    path = Path(__file__).parent / "fixtures" / "inspect_tiny_qa.eval"
    log = read_eval_log(str(path))
    log.samples[0].scores["match"].value = value
    monkeypatch.setattr("inspect_ai.log.read_eval_log", lambda _: log)
    assert load_inspect_log(path).score[0] == expected


def test_unknown_inspect_grade_in_a_real_json_log_fails_without_traceback(tmp_path: Path) -> None:
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    original = Path(__file__).parent / "fixtures" / "inspect_tiny_qa.eval"
    log = read_eval_log(str(original))
    log.samples[0].scores["match"].value = "pending"
    path = tmp_path / "unknown.json"
    path.write_text(log.model_dump_json())
    result = run_cli("summarize", str(path), "--json")
    assert result.returncode != 0
    assert "sample 1:" in result.stderr and "grade" in result.stderr
    assert "Traceback" not in result.stderr and not result.stdout


@pytest.mark.parametrize("doc_id", [None, "", {"q": 1}, [1]])
def test_harness_document_identity_cannot_be_invented_from_row_order(tmp_path: Path, doc_id) -> None:
    from errorbars.adapters.lm_eval import load_lm_eval_samples

    path = tmp_path / "samples_task_2026-10-04T12-00-00.jsonl"
    path.write_text(json.dumps({"doc_id": doc_id, "metrics": ["acc"], "acc": 1}))
    with pytest.raises(ValueError, match="doc_id"):
        load_lm_eval_samples(path, model="a")


def test_harness_document_id_is_required(tmp_path: Path) -> None:
    from errorbars.adapters.lm_eval import load_lm_eval_samples

    path = tmp_path / "samples_task_2026-10-04T12-00-00.jsonl"
    path.write_text('{"metrics":["acc"],"acc":1}\n')
    with pytest.raises(ValueError, match="doc_id"):
        load_lm_eval_samples(path, model="a")


def test_bootstrap_allocation_is_bounded_and_matches_one_shot_seeded_oracle(monkeypatch) -> None:
    values = np.linspace(-0.3, 0.8, 101)
    count, seed = 4101, 73
    generator = np.random.default_rng(seed)
    naive = values[generator.integers(0, len(values), size=(count, len(values)))].mean(axis=1)
    real_default_rng = np.random.default_rng
    allocated: list[int] = []

    class TrackedGenerator:
        def __init__(self, seed):
            self.real = real_default_rng(seed)

        def integers(self, low, high, *, size):
            allocated.append(int(np.prod(size)))
            return self.real.integers(low, high, size=size)

    monkeypatch.setattr(np.random, "default_rng", TrackedGenerator)
    result = bootstrap_ci(values, n_boot=count, seed=seed)
    assert result.ci_low == np.quantile(naive, 0.025)
    assert result.ci_high == np.quantile(naive, 0.975)
    assert result.se == pytest.approx(np.std(naive, ddof=1), rel=1e-14)
    assert max(allocated) <= 250_000
    assert sum(allocated) == count * len(values)


@pytest.mark.parametrize("count", [0, 1, -1, 2.5, float("inf"), True])
def test_bootstrap_resample_counts_are_actual_integer_counts(count) -> None:
    with pytest.raises(ValueError, match="n_boot"):
        bootstrap_ci([0.0, 1.0], n_boot=count)


@pytest.mark.parametrize("scale", [1e-200, 1e-100, 1.0, 1e100])
def test_dimensionless_icc_does_not_disappear_with_tiny_score_units(scale: float) -> None:
    scores = np.repeat([1.0, 5.0, 9.0, 20.0], 3)
    groups = np.repeat([0, 1, 2, 3], 3)
    assert intraclass_correlation(scores * scale, groups) == pytest.approx(1.0)


@pytest.mark.parametrize("groups", [[0, 1, 2, 3], [0, 0, 1, 1]])
def test_unrepresentable_variance_components_do_not_become_zero(groups) -> None:
    with pytest.raises(ValueError, match="too small.*rescale"):
        within_between_variance(np.array([1.0, 2.0, 3.0, 4.0]) * 1e-200, groups)


@pytest.mark.parametrize(
    "a,b,expected_reduction", [([1, 1], [0, 0], None), ([1, 1], [0, 1], 0.0), ([0, 1], [0, 0], 0.0)]
)
def test_undefined_correlation_is_not_zero(a, b, expected_reduction) -> None:
    result = paired_compare(a, b)
    assert result.correlation is None
    assert result.variance_reduction == expected_reduction
    assert result.as_dict()["correlation"] is None
    assert any("Correlation" in note for note in result.warnings)
    assert result.mcnemar is not None


def test_unavailable_pairing_fields_survive_cli_and_strict_json(tmp_path: Path) -> None:
    path = tmp_path / "constant.csv"
    path.write_text("question_id,model,score\nq1,a,1\nq2,a,1\nq1,b,0\nq2,b,0\n")
    text = run_cli("compare", str(path))
    assert text.returncode == 0, text.stderr
    assert text.stdout.count("unavailable") >= 2
    raw = run_cli("compare", str(path), "--json")
    assert raw.returncode == 0, raw.stderr
    report = json.loads(raw.stdout)
    assert report["correlation"] is report["variance_reduction"] is None
    assert report["p_value"] == 0.0 and "mcnemar" in report
