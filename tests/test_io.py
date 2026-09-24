from __future__ import annotations

import json

import pytest

from errorbars.io import ColumnMap, load_csv, load_jsonl


def test_load_csv_basic(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("question_id,model,score\nq1,gpt,1\nq1,claude,0\nq2,gpt,0\n")
    data = load_csv(p)
    assert len(data) == 3
    assert data.models() == ["gpt", "claude"]
    assert data.score == [1.0, 0.0, 0.0]


def test_load_csv_with_cluster_and_custom_columns(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("qid,passage,mdl,acc\nq1,p1,gpt,0.8\nq2,p1,gpt,0.6\n")
    cols = ColumnMap(question_id="qid", model="mdl", score="acc", cluster_id="passage", sample=None)
    data = load_csv(p, cols)
    assert data.cluster_id == ["p1", "p1"]
    assert data.score == [0.8, 0.6]


def test_load_csv_missing_required_column_raises(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("question_id,model\nq1,gpt\n")
    with pytest.raises(ValueError, match="score"):
        load_csv(p)


def test_load_csv_bad_score_value_raises(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("question_id,model,score\nq1,gpt,not-a-number\n")
    with pytest.raises(ValueError, match="score"):
        load_csv(p)


def test_load_csv_empty_file_raises(tmp_path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("question_id,model,score\n")
    with pytest.raises(ValueError, match="no rows"):
        load_csv(p)


def test_load_jsonl_basic(tmp_path) -> None:
    p = tmp_path / "data.jsonl"
    rows = [
        {"question_id": "q1", "model": "gpt", "score": 1},
        {"question_id": "q1", "model": "claude", "score": 0},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    data = load_jsonl(p)
    assert len(data) == 2
    assert data.score == [1.0, 0.0]


def test_load_jsonl_skips_blank_lines(tmp_path) -> None:
    p = tmp_path / "data.jsonl"
    p.write_text('{"question_id": "q1", "model": "gpt", "score": 1}\n\n\n')
    data = load_jsonl(p)
    assert len(data) == 1


def test_load_jsonl_bad_json_reports_line_number(tmp_path) -> None:
    p = tmp_path / "data.jsonl"
    p.write_text('{"question_id": "q1", "model": "gpt", "score": 1}\nnot json\n')
    with pytest.raises(ValueError, match="line 2|:2:"):
        load_jsonl(p)


def test_scores_by_question_averages_repeated_samples() -> None:
    from errorbars.io import EvalData

    data = EvalData(
        question_id=["q1", "q1", "q2"],
        model=["m", "m", "m"],
        score=[1.0, 0.0, 1.0],
        sample=["0", "1", "0"],
    )
    result = data.scores_by_question()
    assert result == {"q1": 0.5, "q2": 1.0}
