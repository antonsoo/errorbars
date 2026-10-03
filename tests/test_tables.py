"""What the table commands print, as a reader of a CI log or a plain install sees it."""

from __future__ import annotations

import csv
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from errorbars._tables import Output, Table, plain_table

REPO_ROOT = Path(__file__).parent.parent

# Names as harnesses and people write them: an lm-eval directory name, a quantization tag in
# brackets, an Ollama-style tag between colons, and one that is a closing tag to rich.
LONG_A = "meta-llama__Llama-3.1-8B-Instruct[q4_k_m]"
LONG_B = "meta-llama__Llama-3.1-70B-Instruct[q4_k_m]"
COLONS = "qwen3:100:latest"
CLOSING = "[/b]run-2"
MODELS = {LONG_A: 0.55, LONG_B: 0.7, COLONS: 0.6, CLOSING: 0.4}


@pytest.fixture(scope="module")
def scores(tmp_path_factory: pytest.TempPathFactory) -> Path:
    rng = random.Random(7)
    path = tmp_path_factory.mktemp("tables") / "scores.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "model", "score"])
        for q in range(120):
            for model, p in MODELS.items():
                writer.writerow([f"q{q}", model, int(rng.random() < p)])
    return path


def run_cli(
    *args: str, hide_rich: bool = False, pipe_encoding: str | None = None
) -> subprocess.CompletedProcess[str]:
    # `sys.modules["rich"] = None` makes `import rich` fail the way it does when the package
    # isn't installed, which is what `pip install errorbars` (no extra) gives.
    hide = "sys.modules['rich'] = None; " if hide_rich else ""
    code = (
        f"import sys; {hide}from errorbars.cli import main; "
        "sys.argv = ['errorbars', *sys.argv[1:]]; main()"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    if pipe_encoding:
        # What Python on Windows gives a redirected stdout: the system's code page.
        env["PYTHONIOENCODING"] = pipe_encoding
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        env=env,
    )


@pytest.mark.parametrize("hide_rich", [False, True], ids=["rich", "plain"])
class TestNamesArePrintedAsTheyAre:
    def test_leaderboard_prints_every_name_whole(self, scores: Path, hide_rich: bool) -> None:
        result = run_cli("leaderboard", str(scores), hide_rich=hide_rich)
        assert result.returncode == 0, result.stderr
        for name in MODELS:
            # Once in the leaderboard and three times in the six pairwise rows.
            assert result.stdout.count(name) == 4, name
        assert "\u2026" not in result.stdout  # no cell was cut short with an ellipsis

    def test_compare_prints_both_names(self, scores: Path, hide_rich: bool) -> None:
        result = run_cli(
            "compare", str(scores), "--model-a", LONG_A, "--model-b", CLOSING, hide_rich=hide_rich
        )
        assert result.returncode == 0, result.stderr
        assert f"mean({LONG_A})" in result.stdout
        assert f"mean({CLOSING})" in result.stdout

    def test_summarize_and_power(self, scores: Path, hide_rich: bool) -> None:
        result = run_cli("summarize", str(scores), "--model", COLONS, hide_rich=hide_rich)
        assert result.returncode == 0, result.stderr
        assert f"summarize: {COLONS}" in result.stdout
        result = run_cli("power", "--delta", "0.03", "--baseline", "0.7", hide_rich=hide_rich)
        assert result.returncode == 0, result.stderr
        assert "Questions needed: " in result.stdout
        result = run_cli("power", "--n", "500", "--baseline", "0.7", hide_rich=hide_rich)
        assert "Minimum detectable effect at n=500: " in result.stdout


def test_a_plain_install_prints_tables_as_text(scores: Path) -> None:
    result = run_cli("leaderboard", str(scores), hide_rich=True)
    lines = result.stdout.splitlines()
    assert lines[0] == "leaderboard"
    assert lines[1].split() == ["rank", "model", "mean", "95%", "CI", "n", "group"]
    assert set(lines[2]) == {"-", " "}
    # Columns line up: every row is as long as the rule, give or take the last cell.
    assert all(len(line) <= len(lines[2]) for line in lines[3:7])
    assert lines[3].startswith("   1  ")
    assert all(ord(ch) < 128 for ch in result.stdout)


def test_plain_table_alignment() -> None:
    table = Table(title="t")
    table.add_column("name")
    table.add_column("value", justify="right")
    table.add_row("a", "1.5")
    table.add_row("longer name", "10")
    assert plain_table(table).splitlines() == [
        "t",
        "name         value",
        "-----------  -----",
        "a              1.5",
        "longer name     10",
    ]


def test_plain_table_without_rows() -> None:
    table = Table(title="empty")
    table.add_column("a")
    assert plain_table(table).splitlines() == ["empty", "a", "-"]


def test_rich_folds_names_in_a_narrow_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("rich")
    from rich.console import Console

    class Narrow(Output):
        def _console(self, width: int | None = None) -> Console:
            # Rich snapshots the terminal environment at import time. In a dumb
            # terminal it ignores width and uses 80 columns, even with force_terminal.
            return Console(
                markup=False,
                width=40,
                force_terminal=True,
                color_system=None,
                _environ={"TERM": "xterm-256color"},
            )

    table = Table(title="leaderboard")
    table.add_column("model")
    table.add_column("95% CI", justify="right")
    table.add_row(LONG_A, "[0.5004, 0.6130]")
    Narrow().table(table)
    out = capsys.readouterr().out
    assert "[0.5004, 0.6130]" in out  # the numbers stay on one line
    first_cells = [line.split("\u2502")[1].strip() for line in out.splitlines() if "\u2502" in line]
    assert len(first_cells) > 1
    assert "".join(first_cells) == LONG_A  # the name is folded over several lines, not cut
    assert "\u2026" not in out


@pytest.mark.parametrize("hide_rich", [False, True], ids=["rich", "plain"])
def test_a_pipe_carries_any_model_name(tmp_path: Path, hide_rich: bool) -> None:
    # A redirected stdout on Windows is cp1252, which has no Chinese: the table commands
    # stopped with "'charmap' codec can't encode characters". A pipe gets UTF-8.
    names = {"\u901a\u4e49\u5343\u95ee-72B": 0.7, "Llama-3.1-8B": 0.5}
    rng = random.Random(3)
    path = tmp_path / "scores.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "model", "score"])
        for q in range(80):
            for model, p in names.items():
                writer.writerow([f"q{q}", model, int(rng.random() < p)])
    result = run_cli("leaderboard", str(path), hide_rich=hide_rich, pipe_encoding="cp1252")
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("\u901a\u4e49\u5343\u95ee-72B") == 2
    missing = run_cli("summarize", str(path), "--model", "\u6a21\u578b", pipe_encoding="cp1252")
    assert missing.returncode != 0
    assert "no model '\u6a21\u578b' in the data" in missing.stderr


@pytest.mark.parametrize("hide_rich", [False, True], ids=["rich", "plain"])
def test_an_escape_sequence_in_a_name_is_shown_not_run(tmp_path: Path, hide_rich: bool) -> None:
    # A model name holding a terminal escape sequence (this one retitles the window) was sent
    # to the terminal as it was, in the tables and in errors that list the models.
    osc = "\x1b]0;pwned\x07"
    path = tmp_path / "scores.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "model", "score"])
        for q in range(40):
            writer.writerow([f"q{q}", f"m{osc}", q % 2])
            writer.writerow([f"q{q}", "other", (q // 2) % 2])
    result = run_cli("leaderboard", str(path), hide_rich=hide_rich)
    assert result.returncode == 0, result.stderr
    assert "\x1b]" not in result.stdout and "\x07" not in result.stdout
    assert "m\\x1b]0;pwned\\x07" in result.stdout
    missing = run_cli("summarize", str(path), "--model", "nope", hide_rich=hide_rich)
    assert missing.returncode != 0
    assert "\x1b" not in missing.stderr and "m\\x1b]0;pwned\\x07" in missing.stderr


def test_visible_leaves_text_and_escapes_controls() -> None:
    from errorbars._tables import visible

    assert visible("plain\ttext\nline") == "plain\ttext\nline"
    assert visible("a\x1bb\x9bc\x00") == "a\\x1bb\\x9bc\\x00"
