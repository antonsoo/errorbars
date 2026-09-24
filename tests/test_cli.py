from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DATA = REPO_ROOT / "examples" / "data" / "reading_comprehension.csv"
LMEVAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "samples_copa_2026-09-24T03-04-37.941131.jsonl"
INSPECT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "inspect_tiny_qa.eval"


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


def test_cli_import_lm_eval(tmp_path) -> None:
    out = tmp_path / "converted.csv"
    result = run_cli("import", "lm-eval", str(LMEVAL_FIXTURE), "--model", "dummy-copa", "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert "wrote 20 rows" in result.stdout
    rows = out.read_text().strip().splitlines()
    assert rows[0] == "question_id,model,score"
    assert len(rows) == 21
    assert rows[1] == "copa-0,dummy-copa,0.0"

    # The converted CSV should be directly usable by the rest of the CLI.
    summarize = run_cli("summarize", str(out), "--json")
    assert summarize.returncode == 0, summarize.stderr
    payload = json.loads(summarize.stdout)
    assert payload["n"] == 20


def test_cli_import_lm_eval_requires_model() -> None:
    result = run_cli("import", "lm-eval", str(LMEVAL_FIXTURE), "-o", "/dev/null")
    assert result.returncode != 0
    assert "--model" in result.stderr


def test_cli_import_lm_eval_custom_metric(tmp_path) -> None:
    arc = REPO_ROOT / "tests" / "fixtures" / "samples_arc_easy_2026-09-24T03-05-32.831346.jsonl"
    out = tmp_path / "converted.csv"
    result = run_cli("import", "lm-eval", str(arc), "--model", "m", "--metric", "acc_norm", "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert "wrote 5 rows" in result.stdout


def test_cli_import_inspect(tmp_path) -> None:
    out = tmp_path / "converted.csv"
    result = run_cli("import", "inspect", str(INSPECT_FIXTURE), "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert "wrote 5 rows" in result.stdout
    rows = out.read_text().strip().splitlines()
    assert rows[0] == "question_id,model,score,sample"
    assert len(rows) == 6


def test_cli_import_unknown_adapter_rejected() -> None:
    result = run_cli("import", "not-a-real-adapter", str(LMEVAL_FIXTURE), "-o", "/dev/null")
    assert result.returncode != 0
