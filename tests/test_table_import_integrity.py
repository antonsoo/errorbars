from __future__ import annotations

import csv
import io
import warnings

import pytest

from errorbars.io import ColumnMap, load_csv, load_dataframe


@pytest.mark.parametrize("column", ["score", "question_id", "model", "cluster_id", "sample", "note"])
def test_dataframe_duplicate_columns_fail_without_loss_or_mutation(column: str) -> None:
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"question_id": ["q1", "q2"], "model": ["a", "a"], "score": [1, 0]})
    if column not in frame:
        frame[column] = ["first", "first"]
    frame.insert(len(frame.columns), column, ["second", "second"], allow_duplicates=True)
    original = frame.copy(deep=True)
    # The former to_dict call warns, discards the first column, and keeps going.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(ValueError, match=f"duplicate DataFrame columns: {column}"):
            load_dataframe(frame)
    pd.testing.assert_frame_equal(frame, original)


def test_dataframe_duplicate_row_indexes_are_not_duplicate_observations() -> None:
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(
        {"qid": ["q1", "q2"], "mdl": ["a", "a"], "acc": [0.5, 1.0], "passage": ["p", "p"]},
        index=[7, 7],
    )
    data = load_dataframe(frame, ColumnMap(question_id="qid", model="mdl", score="acc", cluster_id="passage"))
    assert data.question_id == ["q1", "q2"]
    assert data.score == [0.5, 1.0]
    assert data.cluster_id == ["p", "p"]


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ('question_id,model,score\nq1,a,1\nq2,a,"0', 3),
        ('question_id,model,score\nq1,a,1\nq2,a,"0"junk\n', 3),
        ('question_id,model,score\nq1,a,1\n"q2\ncontinued,a,0', 4),
        ('question_id,model,"score', 1),
        ('question_id,model,"score"junk\nq1,a,1\n', 1),
    ],
)
def test_csv_quote_errors_report_consumed_physical_line(tmp_path, text: str, line: int) -> None:
    path = tmp_path / "damaged.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=rf"damaged\.csv:{line}: invalid CSV:"):
        load_csv(path)


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("final_newline", [False, True])
def test_csv_writer_output_keeps_quotes_multiline_and_closed_eof(
    tmp_path, delimiter: str, newline: str, final_newline: bool
) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator=newline, quoting=csv.QUOTE_ALL)
    writer.writerow(["question_id", "model", "score"])
    writer.writerow(['question "one"', "model,a;b\tc", "1"])
    writer.writerow(["question\ncontinued", "model,a;b\tc", "0.5" if delimiter == "," else "0,5"])
    text = output.getvalue()
    if not final_newline:
        text = text[: -len(newline)]
    path = tmp_path / "valid.csv"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode())
    data = load_csv(path)
    assert data.question_id == ['question "one"', "question\ncontinued"]
    assert data.model == ["model,a;b\tc"] * 2
    assert data.score == [1.0, 0.5]
    assert [(source.line_start, source.line_end) for source in data.sources] == [(2, 2), (3, 4)]


def test_csv_field_limit_becomes_located_value_error(tmp_path) -> None:
    path = tmp_path / "large.csv"
    path.write_text("question_id,model,score\n" + "q" * (csv.field_size_limit() + 1) + ",a,1\n")
    with pytest.raises(ValueError, match=r"large\.csv:2: invalid CSV: field larger than field limit"):
        load_csv(path)
