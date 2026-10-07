from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from errorbars.cli import main
from errorbars.io import EvalData, load_csv
from errorbars.report import comparison_html, write_comparison_html
from errorbars.review import review_comparison

ROOT = Path(__file__).resolve().parents[1]


def _payload(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html)
    return json.loads(match.group(1))


def test_report_escapes_imported_markup_and_keeps_exact_evidence():
    model = '</script><script>window.pwned=true</script>\u202e\ud800'
    question = '=1+1<img src="https://example.invalid/">'
    data = EvalData([question, "q2"] * 2, [model] * 2 + ["B"] * 2, [1, 0, 0, 1])
    review = review_comparison(data, model, "B")
    html = comparison_html(review)
    assert html.count("<script") == 2
    assert "<img" not in html
    assert "</script><script>window.pwned" not in html
    assert "\\u202e" in html
    assert _payload(html) == review.as_dict()
    html.encode("utf-8")  # Unpaired surrogate identifiers must not break output writing.


def test_csp_hashes_match_the_actual_scripts_and_styles():
    data = EvalData(["q1", "q2"] * 2, ["A"] * 2 + ["B"] * 2, [1, 0, 0, 1])
    html = comparison_html(review_comparison(data, "A", "B"))
    for tag in ("script", "style"):
        body = re.search(f"<{tag}>(.*?)</{tag}>", html, re.DOTALL).group(1)
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        assert f"sha256-{digest}" in html
    assert "connect-src &#x27;none&#x27;" in html
    assert "unsafe-inline" not in html and "unsafe-eval" not in html
    assert "SIL OPEN FONT LICENSE" in html


def test_cli_writes_evidence_without_polluting_json_stdout(tmp_path, capsys):
    output = tmp_path / "result.html"
    main(["compare", str(ROOT / "examples/data/reading_comprehension.csv"), "--model-a", "tuned-70b",
          "--model-b", "baseline-70b", "--html", str(output), "--json"])
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    embedded = _payload(output.read_text())
    assert embedded["comparison"]["mean_diff"] == result["mean_diff"]
    assert embedded["cohort"]["n_shared"] == result["n"]
    assert len(embedded["questions"]) == 200
    assert len(embedded["clusters"]) == 40
    assert "wrote comparison evidence" in captured.err


def test_cli_can_export_missing_cohort_while_refusing_inference(tmp_path, capsys):
    input_path = tmp_path / "missing.csv"
    input_path.write_text("question_id,model,score\na,A,1\nb,A,0\nx,B,0\ny,B,1\n")
    output = tmp_path / "missing.html"
    with pytest.raises(SystemExit, match="fewer than 2"):
        main(["compare", str(input_path), "--html", str(output), "--json"])
    captured = capsys.readouterr()
    assert not captured.out
    payload = _payload(output.read_text())
    assert payload["comparison"] is None
    assert payload["cohort"]["n_shared"] == 0
    assert len(payload["questions"]) == 4


def test_failed_replacement_preserves_previous_report(tmp_path, monkeypatch):
    output = tmp_path / "existing.html"
    output.write_text("previous report")
    data = load_csv(ROOT / "examples/data/reading_comprehension.csv")
    review = review_comparison(data, "tuned-70b", "baseline-70b")

    def fail(*args):
        raise OSError("cannot replace")

    monkeypatch.setattr("errorbars.report.os.replace", fail)
    with pytest.raises(OSError, match="cannot replace"):
        write_comparison_html(review, output)
    assert output.read_text() == "previous report"
    assert list(tmp_path.iterdir()) == [output]


def test_report_rejects_input_extension_as_output(tmp_path):
    output = tmp_path / "scores.csv"
    original = "question_id,model,score\na,A,1\nb,A,0\na,B,0\nb,B,1\n"
    output.write_text(original)
    with pytest.raises(SystemExit, match="must end in .html"):
        main(["compare", str(output), "--html", str(output)])
    assert output.read_text() == original
