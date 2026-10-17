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


def test_public_partial_run_exports_exactly_the_native_observed_outcomes() -> None:
    model = "20260901_mini-v2.4.2_gemini-3-5-flash"
    native = json.loads((ROOT / "studies/observed-cohorts/native/partial-details.json").read_text())
    result = subprocess.run([sys.executable, str(SCRIPT), model], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert len(rows) == len(native) == 441
    assert sum(int(row["score"]) for row in rows) == 359
    assert {row["question_id"]: bool(int(row["score"])) for row in rows} == {
        iid: detail["resolved"] for iid, detail in native.items()
    }
    assert "59 unobserved tasks omitted" in result.stderr
    assert "not the official full-benchmark score" in result.stderr


@pytest.mark.parametrize("changes", [
    {"evaluated": None}, {"evaluated": False}, {"evaluated": 2}, {"evaluated": "zz"},
    {"evaluated": "-1"}, {"evaluated": "0x1f"}, {"evaluated": "20"}, {"evaluated": "00001f"},
    {"evaluated": "0f", "n_evaluated": 4},  # The resolved high bit lies outside this cohort.
    {"n_evaluated": 4}, {"n_evaluated": True}, {"n_resolved": 2}, {"n_resolved": True},
])
def test_inconsistent_masks_are_refused_before_any_csv_is_written(tmp_path, changes) -> None:
    sub = {"id": "partial", "resolved": "10", "n_resolved": 1, "evaluated": "1f", "n_evaluated": 5}
    source = tmp_path / "outcomes.json"
    source.write_text(json.dumps({
        "instances": [f"repo__project-{i}" for i in range(5)], "submissions": [{**sub, **changes}],
    }))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "partial", "--data", str(source)], capture_output=True, text=True,
    )
    assert result.returncode == 1 and not result.stdout
    assert "error:" in result.stderr and "Traceback" not in result.stderr


def test_partial_count_without_a_mask_does_not_guess_which_tasks_were_observed(tmp_path) -> None:
    source = tmp_path / "outcomes.json"
    source.write_text(json.dumps({
        "instances": ["repo__project-1", "repo__project-2"],
        "submissions": [{"id": "partial", "resolved": "1", "n_resolved": 1, "n_evaluated": 1}],
    }))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "partial", "--data", str(source)], capture_output=True, text=True,
    )
    assert result.returncode == 1 and not result.stdout
    assert "n_evaluated must match" in result.stderr
