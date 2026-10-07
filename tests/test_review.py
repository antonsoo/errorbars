from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import statsmodels.api as sm

from errorbars.adapters.lm_eval import load_lm_eval_samples
from errorbars.inputs import load_inputs
from errorbars.io import EvalData, concat, load_csv, load_jsonl
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]


def test_repeated_generations_and_missing_questions_keep_the_actual_cohort(tmp_path):
    path = tmp_path / "scores.csv"
    path.write_text(
        "question_id,model,score,sample,cluster_id\n"
        "q1,A,1,1,p1\nq1,A,1,2,p1\nq1,A,0,3,p1\nq1,B,0,1,p1\n"
        "q2,A,0,1,p1\nq2,B,1,1,p1\nq3,A,1,1,p2\nq3,B,1,1,p2\n"
        "absent-from-B,A,1,1,p3\nabsent-from-A,B,0,1,p4\n"
    )
    review = review_comparison(load_csv(path), "A", "B")
    assert review.comparison is not None
    assert review.comparison.mean_a == pytest.approx(5 / 9)
    assert review.comparison.mean_b == pytest.approx(2 / 3)
    assert review.comparison.mean_diff == pytest.approx(-1 / 9)
    assert review.cohort["n_shared"] == 3
    assert review.cohort["n_only_a"] == review.cohort["n_only_b"] == 1
    assert review.cohort["n_observations_a"] == 6
    assert review.cohort["n_shared_observations_a"] == 5
    assert review.cohort["mean_all_a"] == pytest.approx(2 / 3)
    q = next(q for q in review.questions if q.question_id == "q1")
    assert [o.sample for o in q.observations_a] == ["1", "2", "3"]
    assert [o.line_start for o in q.observations_a] == [2, 3, 4]
    for q in review.questions:
        if q.presence != "shared":
            assert q.difference is None
            assert (q.mean_a is None) != (q.mean_b is None)
    assert len(review.questions) == 5
    groups = {c.cluster_id: c for c in review.clusters}
    assert groups["p1"].without_difference == 0
    assert groups["p2"].without_difference == pytest.approx(-1 / 6)
    assert sum(c.contribution for c in review.clusters) == pytest.approx(-1 / 9)
    payload = review.as_dict()
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    assert payload["sources"] == [{"id": 0, "name": "scores.csv"}]
    assert str(tmp_path) not in json.dumps(payload)


def test_cluster_intervals_and_deletions_match_independent_calculations():
    data = load_csv(ROOT / "examples/data/reading_comprehension.csv")
    review = review_comparison(data, "tuned-70b", "baseline-70b", confidence=0.9)
    assert review.comparison is not None
    a, b = {}, {}
    clusters = {}
    for i, (qid, model, score) in enumerate(zip(data.question_id, data.model, data.score, strict=True)):
        if model == "tuned-70b":
            a[qid] = score
        if model == "baseline-70b":
            b[qid] = score
        clusters[qid] = data.cluster_id[i]
    ids = sorted(a.keys() & b.keys())
    diff = np.array([a[q] - b[q] for q in ids])
    groups = [clusters[q] for q in ids]
    oracle = sm.OLS(diff, np.ones((len(ids), 1))).fit(
        cov_type="cluster", cov_kwds={"groups": groups}, use_t=True
    )
    assert review.comparison.se_clustered == pytest.approx(oracle.bse[0])
    assert review.comparison.p_value_clustered == pytest.approx(oracle.pvalues[0])
    assert review.comparison.ci_low_clustered == pytest.approx(oracle.conf_int(alpha=0.1)[0, 0])
    for c in review.clusters:
        retained = [a[q] - b[q] for q in ids if clusters[q] != c.cluster_id]
        assert c.without_difference == pytest.approx(np.mean(retained))
        assert c.shift == pytest.approx(np.mean(retained) - diff.mean())


def test_deleting_a_dominant_cluster_retains_small_remainders():
    data = EvalData(
        ["a", "b", "c", "d"] * 2, ["A"] * 4 + ["B"] * 4,
        [1e30, 1e30, 1, 3] + [0] * 4, ["large", "large", "small", "small"] * 2,
    )
    review = review_comparison(data, "A", "B")
    group = next(c for c in review.clusters if c.cluster_id == "large")
    assert group.without_difference == 2


@pytest.mark.parametrize("ids_b,groups,reason", [
    (["x", "y"], None, "fewer than 2"),
    (["a", "x"], None, "fewer than 2"),
    (["a", "b"], ["one"] * 4, "2 independent clusters"),
])
def test_unavailable_inference_still_has_a_complete_ledger(ids_b, groups, reason):
    data = EvalData(["a", "b", *ids_b], ["A", "A", "B", "B"], [1, 0, 0, 1], groups)
    review = review_comparison(data, "A", "B")
    assert review.comparison is None
    assert reason in review.unavailable_reason
    assert len(review.questions) == len(set(data.question_id))
    json.dumps(review.as_dict(), allow_nan=False)


def test_sources_survive_multiline_csv_blank_json_lines_concat_and_model_selection(tmp_path):
    csv = tmp_path / "a.csv"
    csv.write_text('question_id,model,score\n"multi\nline",A,1\nplain,A,0\n')
    ndjson = tmp_path / "b.jsonl"
    ndjson.write_text('\n{"question_id":"multi\\nline","model":"B","score":0}\n\n'
                      '{"question_id":"plain","model":"B","score":1}\n')
    data = concat([(str(csv), load_csv(csv)), (str(ndjson), load_jsonl(ndjson))])
    a = data.filter_model("A")
    assert [(s.record, s.line_start, s.line_end) for s in a.sources] == [(1, 2, 3), (2, 4, 4)]
    b = data.filter_model("B")
    assert [(s.record, s.line_start, s.line_end) for s in b.sources] == [(1, 2, 2), (2, 4, 4)]


def test_real_harness_scores_keep_record_metric_and_filter_locations():
    loaded = load_inputs([ROOT / "tests/fixtures/lm_eval_output"])
    a, b = loaded.data.models()
    review = review_comparison(loaded.data, a, b)
    assert review.cohort["n_shared"] == 20
    for q in review.questions:
        for obs in q.observations_a + q.observations_b:
            assert obs.metric == "acc"
            assert obs.filter == "none"
            assert obs.line_start == obs.line_end == obs.record
    filtered_path = next((ROOT / "tests/fixtures").glob("samples_gsm8k*"))
    filtered = load_lm_eval_samples(filtered_path, model="m", filter_name="maj@8")
    raw_lines = filtered_path.read_text().splitlines()
    for source in filtered.sources:
        record = json.loads(raw_lines[source.line_start - 1])
        assert record["filter"] == "maj@8"
        assert source.filter == "maj@8"


def test_unrelated_models_are_excluded_and_unknown_locations_are_explicit():
    data = EvalData(["q1", "q2"] * 3, ["A"] * 2 + ["B"] * 2 + ["private-model"] * 2,
                    [1, 0, 0, 1, 1, 1])
    review = review_comparison(data, "A", "B")
    assert review.sources == []
    assert all(o.source is None for q in review.questions for o in q.observations_a + q.observations_b)
    assert "private-model" not in json.dumps(review.as_dict())
    with pytest.raises(ValueError, match="different models"):
        review_comparison(data, "A", "A")
