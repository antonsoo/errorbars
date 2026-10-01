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


@pytest.mark.parametrize("bad", ["nan", "NaN", "inf", "-inf"])
def test_non_finite_scores_are_rejected_with_their_row(tmp_path, bad: str) -> None:
    # A NaN used to flow into every mean and p-value, and sorted to the top of the leaderboard.
    p = tmp_path / "data.csv"
    p.write_text(f"question_id,model,score\nq1,a,1\nq2,a,{bad}\n")
    with pytest.raises(ValueError, match=rf"row 2: score '{bad}' is not a finite number"):
        load_csv(p)


def test_duplicate_model_question_rows_are_rejected(tmp_path) -> None:
    # Counting the same question twice inflates n and shrinks every standard error.
    p = tmp_path / "data.csv"
    p.write_text("question_id,model,score\nq1,a,1\nq2,a,0\nq1,a,1\n")
    with pytest.raises(ValueError, match=r"row 3: model 'a' already has a score for question 'q1' \(row 1\)"):
        load_csv(p)


def test_repeated_generations_with_distinct_sample_ids_load(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("question_id,model,score,sample\nq1,a,1,0\nq1,a,0,1\nq1,b,1,0\n")
    data = load_csv(p)
    assert len(data) == 3
    assert data.filter_model("a").scores_by_question() == {"q1": 0.5}


@pytest.mark.parametrize("line", ["[1, 2]", "5", "null", '"q1"'])
def test_jsonl_line_that_is_not_an_object_is_reported_with_its_line(tmp_path, line: str) -> None:
    p = tmp_path / "data.jsonl"
    p.write_text(f'{{"question_id": "q1", "model": "a", "score": 1}}\n{line}\n')
    with pytest.raises(ValueError, match=r"data\.jsonl:2: expected a JSON object per line"):
        load_jsonl(p)


def test_csv_row_with_too_few_fields_is_rejected(tmp_path) -> None:
    # The missing cell used to become a model called "None".
    p = tmp_path / "data.csv"
    p.write_text("score,question_id,model\n1,q1,a\n0,q2\n")
    with pytest.raises(ValueError, match=r"row 2: no value for column 'model'"):
        load_csv(p)


def test_csv_row_with_too_many_fields_is_rejected(tmp_path) -> None:
    # An unquoted comma shifts every later cell one column to the right.
    p = tmp_path / "data.csv"
    p.write_text("question_id,model,score\nq1,a,1\nwhat is 1,5 + 1,a,0\n")
    with pytest.raises(ValueError, match=r"row 2: more fields than the header has columns"):
        load_csv(p)


def test_scores_too_large_to_square_are_rejected(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("question_id,model,score\nq1,a,1\nq2,a,1e308\n")
    with pytest.raises(ValueError, match=r"row 2: score '1e308' is too large to analyze"):
        load_csv(p)

