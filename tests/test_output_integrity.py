"""Exports preserve source evidence and previously completed artifacts."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from errorbars._output import atomic_text_output
from errorbars.cli import main
from errorbars.io import load_csv, write_csv

ROWS = b"question_id,model,score\na,A,1\nb,A,0\na,B,0\nb,B,1\n"
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("kind", ["csv", "svg", "html"])
def test_cli_output_cannot_replace_the_target_of_an_input_symlink(tmp_path, kind):
    output = tmp_path / f"export.{kind}"
    output.write_bytes(ROWS)
    source = tmp_path / "input.csv"
    source.symlink_to(output.name)
    if kind == "csv":
        args = ["import", "lm-eval", str(source), "-o", str(output)]
    elif kind == "svg":
        args = ["leaderboard", str(source), "--plot", str(output)]
    else:
        args = ["compare", str(source), "--html", str(output)]
    with pytest.raises(SystemExit, match="output must not replace an input"):
        main(args)
    assert output.read_bytes() == ROWS
    assert source.is_symlink()
    assert len(list(tmp_path.iterdir())) == 2


def test_inferred_model_sidecar_is_protected_even_through_a_link(tmp_path):
    stamp = "2026-09-24T03-04-37.941131"
    name = f"samples_copa_{stamp}.jsonl"
    source = tmp_path / name
    shutil.copyfile(ROOT / "tests/fixtures" / name, source)
    original = source.read_bytes()
    output = tmp_path / "canonical.csv"
    metadata = b'{"model_name":"example"}\n'
    output.write_bytes(metadata)
    sidecar = tmp_path / f"results_{stamp}.json"
    sidecar.symlink_to(output.name)
    with pytest.raises(SystemExit, match="output must not replace an input"):
        main(["import", "lm-eval", str(source), "-o", str(output)])
    assert source.read_bytes() == original
    assert output.read_bytes() == metadata and sidecar.is_symlink()


def test_direct_csv_export_preserves_source_hardlinks(tmp_path):
    source = tmp_path / "input.csv"
    source.write_bytes(ROWS)
    alias = tmp_path / "alias.csv"
    alias.hardlink_to(source)
    with pytest.raises(ValueError, match="output must not replace an input"):
        write_csv(load_csv(source), alias)
    assert alias.samefile(source) and source.read_bytes() == ROWS


@pytest.mark.parametrize("exists", [False, True])
def test_exception_after_a_partial_write_leaves_destination_and_directory_unchanged(tmp_path, exists):
    output = tmp_path / "export.csv"
    if exists:
        output.write_bytes(b"previous report")
    with pytest.raises(OSError, match="storage interrupted"), atomic_text_output(output) as handle:
        handle.write("partial replacement")
        handle.flush()
        raise OSError("storage interrupted")
    assert output.exists() == exists
    if exists:
        assert output.read_bytes() == b"previous report"
    assert list(tmp_path.iterdir()) == ([output] if exists else [])


def test_flush_failure_leaves_previous_report_and_cleans_temporary_file(tmp_path, monkeypatch):
    output = tmp_path / "export.svg"
    output.write_bytes(b"previous report")

    def fail(_fd):
        raise OSError("sync failed")

    monkeypatch.setattr("errorbars._output.os.fsync", fail)
    with pytest.raises(OSError, match="sync failed"), atomic_text_output(output) as handle:
        handle.write("complete but unflushed")
    assert output.read_bytes() == b"previous report"
    assert list(tmp_path.iterdir()) == [output]


def test_private_atomic_csv_replacement_keeps_exact_serialization(tmp_path):
    source = tmp_path / "input.csv"
    source.write_bytes(ROWS)
    output = tmp_path / "export.csv"
    output.write_bytes(b"previous report")
    write_csv(load_csv(source), output)
    expected = b"question_id,model,score\r\na,A,1.0\r\nb,A,0.0\r\na,B,0.0\r\nb,B,1.0\r\n"
    assert output.read_bytes() == expected
    assert source.read_bytes() == ROWS
    if os.name == "posix":
        assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO")
def test_fifo_is_rejected_without_opening_or_removing_it(tmp_path):
    output = tmp_path / "export.svg"
    os.mkfifo(output)
    before = output.stat()
    with pytest.raises(ValueError, match="regular file"), atomic_text_output(output):
        pytest.fail("FIFO opened")
    assert output.stat() == before
