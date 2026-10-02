"""CSV as a spreadsheet saves it, which is where a hand-made score file usually comes from."""

from __future__ import annotations

from pathlib import Path

import pytest

from errorbars.io import load_csv

ROWS = [("q1", "münchen-7b", 1.0), ("q2", "münchen-7b", 0.75), ("q1", "base", 0.0), ("q2", "base", 0.5)]


def _expect(path: Path) -> None:
    data = load_csv(path)
    assert list(zip(data.question_id, data.model, data.score, strict=True)) == ROWS


def test_excel_csv_utf8_has_a_byte_order_mark_and_crlf(tmp_path: Path) -> None:
    # "CSV UTF-8 (Comma delimited)". The mark used to become part of the first column's name:
    # "missing required column 'question_id' in row 1".
    path = tmp_path / "scores.csv"
    body = "question_id,model,score\r\n" + "".join(f"{q},{m},{s}\r\n" for q, m, s in ROWS)
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    _expect(path)


def test_semicolons_and_decimal_commas(tmp_path: Path) -> None:
    # What "CSV" means in a locale whose decimal mark is the comma.
    path = tmp_path / "scores.csv"
    lines = ["question_id;model;score"] + [f"{q};{m};{str(s).replace('.', ',')}" for q, m, s in ROWS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _expect(path)


def test_tabs(tmp_path: Path) -> None:
    path = tmp_path / "scores.csv"
    lines = ["question_id\tmodel\tscore"] + [f"{q}\t{m}\t{s}" for q, m, s in ROWS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _expect(path)


def test_spaces_after_the_commas_of_a_hand_written_header(tmp_path: Path) -> None:
    path = tmp_path / "scores.csv"
    path.write_text("question_id, model, score\nq1,a,1\nq1,b,0\n", encoding="utf-8")
    data = load_csv(path)
    assert data.score == [1.0, 0.0]


def test_a_comma_file_keeps_its_semicolons_and_its_thousands(tmp_path: Path) -> None:
    # The delimiter is decided by the header, so a semicolon in a value changes nothing, and a
    # comma inside a quoted number in a comma-delimited file is still not a decimal mark.
    path = tmp_path / "scores.csv"
    path.write_text('question_id,model,score\nq1,"a;b",1\nq2,"a;b","0,5"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"row 2: could not parse score value '0,5'"):
        load_csv(path)
    path.write_text('question_id,model,score\nq1,"a;b",1\nq2,"a;b",0.5\n', encoding="utf-8")
    assert load_csv(path).model == ["a;b", "a;b"]


def test_a_missing_column_is_reported_with_the_columns_that_are_there(tmp_path: Path) -> None:
    path = tmp_path / "scores.csv"
    path.write_text("id,model,correct\nq1,a,1\n", encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_csv(path)
    assert str(caught.value) == "missing required column 'question_id' in row 1 (it has: id, model, correct)"
    wide = tmp_path / "wide.csv"
    wide.write_text(",".join(f"c{i}" for i in range(40)) + "\n" + ",".join("1" for _ in range(40)) + "\n")
    with pytest.raises(ValueError, match=r"\(it has: c0, c1, .*c9, and 30 more\)"):
        load_csv(wide)
