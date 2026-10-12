"""The public study's CSV exporter must not turn malformed reports into model scores."""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/swe-bench-verified/to_csv.py"
TASK = "astropy__astropy-12907"


def export(tmp_path, report):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--mine", f"my-run={path}"], capture_output=True, text=True
    )


@pytest.mark.parametrize("key", ["resolved_ids", "resolved"])
@pytest.mark.parametrize("value", [None, False, 0, {}, "", TASK, [TASK, None], [[TASK]], {TASK: True}])
def test_malformed_outcomes_never_produce_csv(tmp_path, key, value):
    result = export(tmp_path, {key: value})
    assert result.returncode == 1
    assert not result.stdout
    assert "must be a list of task id strings" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "report",
    [
        {"resolved_ids": [], "resolved": [TASK]},
        {"resolved_ids": [TASK], "resolved": []},
        {"resolved_ids": None, "resolved": [TASK]},
        {"resolved_ids": [TASK], "resolved": None},
    ],
)
def test_aliases_cannot_replace_empty_or_invalid_outcomes(tmp_path, report):
    result = export(tmp_path, report)
    assert result.returncode == 1
    assert not result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ({"resolved_ids": []}, 0),
        ({"resolved": []}, 0),
        ({"resolved_ids": [], "resolved": []}, 0),
        ({"resolved_ids": [TASK]}, 1),
        ({"resolved": [TASK]}, 1),
        ({"resolved_ids": [TASK, TASK], "resolved": [TASK]}, 1),
    ],
)
def test_valid_lists_keep_the_documented_leaderboard_denominator(tmp_path, report, expected):
    result = export(tmp_path, report)
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert len(rows) == 500
    assert sum(int(row["score"]) for row in rows) == expected
    assert {row["model"] for row in rows} == {"my-run"}
