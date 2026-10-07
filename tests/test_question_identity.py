from __future__ import annotations

import json
from pathlib import Path

import pytest

from errorbars.inputs import load_inputs
from errorbars.io import ColumnMap, EvalData, concat, load_csv, load_jsonl, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.report import comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]
SOURCE = next((ROOT / "tests/fixtures/lm_eval_output/sshleifer__tiny-gpt2").glob("samples_*.jsonl"))


def _changed(tmp_path, mutate):
    records = [json.loads(line) for line in SOURCE.read_text().splitlines()]
    mutate(records[0])
    output = tmp_path / SOURCE.name
    output.write_text("\n".join(json.dumps(row) for row in records) + "\n")
    return load_inputs([f"original={SOURCE}", f"changed={output}"]).data


@pytest.mark.parametrize("field", ["doc", "target"])
def test_changed_content_with_identical_ids_and_vendor_hash_blocks_pairing(tmp_path, field):
    def mutate(record):
        if field == "doc":
            record["doc"]["premise"] = "PRIVATE_PROMPT_MARKER_Changed_question"
        else:
            record["target"] = "PRIVATE_TARGET_MARKER_Changed_reference"

    data = _changed(tmp_path, mutate)
    review = review_comparison(data, "original", "changed")
    assert review.comparison is None
    assert review.cohort["mean_difference"] is None
    assert review.cohort["n_identity_conflicting"] == 1
    assert review.cohort["n_identity_matching"] == 19
    q = next(q for q in review.questions if q.question_id == "copa-0")
    assert q.presence == "conflicting" and q.difference is None
    assert q.mean_a == q.mean_b == 0  # The problem is question identity, not the score.
    assert q.observations_a[0].question_hash != q.observations_b[0].question_hash
    with pytest.raises(ValueError, match="conflicting question content"):
        build_leaderboard(data)
    report = comparison_html(review)
    assert "PRIVATE_PROMPT_MARKER" not in report and "PRIVATE_TARGET_MARKER" not in report


def test_prompt_variants_vendor_hash_and_object_key_order_do_not_change_question_identity(tmp_path):
    def mutate(record):
        record["arguments"] = {"prompt": "a deliberately different prompt"}
        record["resps"] = ["a different model response"]
        record["doc_hash"] = "vendor-hash-is-not-used-as-proof"
        record["doc"] = dict(reversed(list(record["doc"].items())))

    data = _changed(tmp_path, mutate)
    review = review_comparison(data, "original", "changed")
    assert review.comparison is not None
    assert review.cohort["n_identity_matching"] == 20
    assert review.comparison.mean_diff == 0


@pytest.mark.parametrize("field,value", [("doc", None), ("doc", {}), ("target", None)])
def test_unavailable_identity_is_not_fabricated_from_ids_or_vendor_hash(tmp_path, field, value):
    data = _changed(tmp_path, lambda record: record.update({field: value}))
    review = review_comparison(data, "original", "changed")
    assert review.comparison is not None
    assert review.cohort["n_identity_matching"] == 19
    assert review.cohort["n_identity_unavailable"] == 1


def test_imported_hashes_survive_csv_and_jsonl_round_trips(tmp_path):
    data = _changed(tmp_path, lambda record: record.update(target="different target"))
    csv = tmp_path / "imported.csv"
    write_csv(data, csv)
    restored = load_csv(csv)
    assert restored.question_hash == data.question_hash
    assert restored.pairing_conflicts("original", "changed") == ["copa-0"]
    ndjson = tmp_path / "canonical.jsonl"
    rows = [{"question_id": q, "model": m, "score": s, "signature": h}
            for q, m, s, h in zip(data.question_id, data.model, data.score, data.question_hash, strict=True)]
    ndjson.write_text("\n".join(json.dumps(row) for row in rows))
    restored_json = load_jsonl(ndjson, ColumnMap(question_hash="signature"))
    assert restored_json.question_hash == data.question_hash


def test_mixed_legacy_sources_do_not_inherit_other_models_identity(tmp_path):
    data = _changed(tmp_path, lambda record: None)
    legacy = data.filter_model("changed")
    legacy.question_hash = None
    mixed = concat([("a", data.filter_model("original")), ("b", legacy)])
    review = review_comparison(mixed, "original", "changed")
    assert review.cohort["n_identity_unavailable"] == 20
    assert review.cohort["n_identity_matching"] == 0
    assert mixed.filter_model("changed").question_hash == [None] * 20
    csv = tmp_path / "mixed.csv"
    write_csv(mixed, csv)
    assert load_csv(csv).question_hash == mixed.question_hash


def test_partially_known_repeated_samples_remain_a_partial_identity_check():
    data = EvalData(
        ["q1", "q1", "q2", "q1", "q2"], ["A", "A", "A", "B", "B"], [1, 0, 1, 1, 0],
        sample=["0", "1", "0", "0", "0"], question_hash=["h1", None, "h2", "h1", "h2"],
    )
    review = review_comparison(data, "A", "B")
    assert review.cohort["n_identity_partial"] == 1
    assert review.cohort["n_identity_matching"] == 1
    data.question_hash[1] = "different"
    with pytest.raises(ValueError, match="conflicting question content across samples"):
        data.scores_by_question()


def test_real_models_retain_matching_question_content():
    data = load_inputs([ROOT / "tests/fixtures/lm_eval_output"]).data
    review = review_comparison(data, *data.models())
    assert review.cohort["n_identity_matching"] == 20
    assert review.comparison.mean_diff == pytest.approx(0.2)  # Directory sort puts random-gpt2 first.
