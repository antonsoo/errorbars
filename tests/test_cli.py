from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DATA = REPO_ROOT / "examples" / "data" / "reading_comprehension.csv"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "errorbars.cli", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


@pytest.mark.skipif(not DATA.exists(), reason="run examples/generate_synthetic.py first")
def test_cli_summarize_json() -> None:
    result = run_cli("summarize", str(DATA), "--model", "tuned-70b", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["model"] == "tuned-70b"
    assert 0.0 <= payload["mean"] <= 1.0
    assert "clustered" in payload


@pytest.mark.skipif(not DATA.exists(), reason="run examples/generate_synthetic.py first")
def test_cli_compare_json() -> None:
    result = run_cli(
        "compare", str(DATA), "--model-a", "tuned-70b", "--model-b", "baseline-70b", "--json"
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "p_value" in payload
    assert "mcnemar" in payload  # binary scores


@pytest.mark.skipif(not DATA.exists(), reason="run examples/generate_synthetic.py first")
def test_cli_leaderboard_json_and_plot(tmp_path) -> None:
    plot_path = tmp_path / "forest.svg"
    result = run_cli("leaderboard", str(DATA), "--json", "--plot", str(plot_path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["entries"]) == 4
    assert plot_path.exists()
    assert "<svg" in plot_path.read_text()


@pytest.mark.skipif(not DATA.exists(), reason="run examples/generate_synthetic.py first")
def test_cli_leaderboard_table_output_no_crash() -> None:
    result = run_cli("leaderboard", str(DATA))
    assert result.returncode == 0, result.stderr
    assert "leaderboard" in result.stdout.lower()


def test_cli_power_questions_needed() -> None:
    result = run_cli("power", "--delta", "0.05", "--baseline", "0.5", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_questions"] > 0


def test_cli_power_mde() -> None:
    result = run_cli("power", "--n", "300", "--baseline", "0.5", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mde"] > 0


def test_cli_power_rejects_both_delta_and_n() -> None:
    result = run_cli("power", "--delta", "0.05", "--n", "300", "--baseline", "0.5")
    assert result.returncode != 0
    assert "error" in result.stderr.lower()


def test_cli_missing_file_reports_error() -> None:
    result = run_cli("summarize", "/nonexistent/path.csv", "--json")
    assert result.returncode != 0


@pytest.mark.skipif(not DATA.exists(), reason="run examples/generate_synthetic.py first")
@pytest.mark.parametrize("ci_method", ["clt", "wilson", "bootstrap"])
def test_cli_summarize_ci_methods(ci_method: str) -> None:
    result = run_cli(
        "summarize", str(DATA), "--model", "tuned-70b", "--ci", ci_method, "--json"
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["method"] == ci_method


@pytest.mark.skipif(not DATA.exists(), reason="run examples/generate_synthetic.py first")
def test_cli_summarize_wilson_rejects_continuous_scores(tmp_path) -> None:
    p = tmp_path / "continuous.csv"
    p.write_text("question_id,model,score\nq1,m,0.3\nq2,m,0.7\nq3,m,0.5\n")
    result = run_cli("summarize", str(p), "--ci", "wilson", "--json")
    assert result.returncode != 0
    assert "binary" in result.stderr.lower()


def test_cli_unrecognized_extension_reports_error(tmp_path) -> None:
    p = tmp_path / "data.txt"
    p.write_text("question_id,model,score\nq1,m,1\n")
    result = run_cli("summarize", str(p), "--json")
    assert result.returncode != 0
    assert "extension" in result.stderr.lower()
