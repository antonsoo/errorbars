"""Seeded fuzz of the command line: whatever the data looks like, a command either
prints a result or exits with a one-line ``error:`` message. Never a traceback, and
never JSON a strict parser would refuse (``NaN``, ``Infinity``).
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from errorbars.cli import main

_SCORES: dict[str, list[Any]] = {
    "binary": [0, 1],
    "graded": [0, 0.25, 0.5, 1, 2, -1, 10],
    "constant": [1],
    "huge": [1e308, -1e308, 1e200, 5e15, 0.5],
    "tiny": [1e-300, 2e-300, 0.0, 1e-310],
    "junk": [0, 1, 1, 0, "", "abc", "nan", "inf", "1e999", " 1 ", None, True, 2**70],
}


def _rows(rng: random.Random) -> tuple[list[dict[str, Any]], list[str]]:
    models = [rng.choice(["a", "b", "gpt", "m 1", "é"]) + str(i) for i in range(rng.choice([1, 2, 2, 3, 5]))]
    kind = rng.choice(["binary"] * 8 + ["graded"] * 6 + ["constant", "constant", "huge", "tiny", "junk"])
    samples = rng.choice([1, 1, 1, 2, 3])
    cluster_size = rng.choice([1, 2, 3, 7])
    with_clusters = rng.random() < 0.6
    rows: list[dict[str, Any]] = []
    for q in range(rng.choice([1, 2, 3, 5, 20, 20, 60, 60])):
        for model in models:
            if rng.random() < 0.05:
                continue  # a model that skipped the question
            for sample in range(samples):
                row: dict[str, Any] = {
                    "question_id": f"q{q}" if q % 2 else q,
                    "model": model,
                    "score": rng.choice(_SCORES[kind])
                    if kind != "graded" or rng.random() < 0.5
                    else round(rng.random(), 3),
                }
                if with_clusters:
                    row["cluster_id"] = f"c{q // cluster_size}"
                if samples > 1:
                    row["sample"] = sample
                rows.append(row)
    return rows, models


def _write(rng: random.Random, rows: list[dict[str, Any]], directory: Path) -> Path:
    damaged = rng.randrange(len(rows)) if rows and rng.random() < 0.12 else -1  # one bad row at most
    if rng.random() < 0.5:
        columns = ["question_id", "model", "score"]
        columns.extend(name for name in ("cluster_id", "sample") if any(name in row for row in rows))
        if rng.random() < 0.05:
            columns.remove(rng.choice(columns))
        lines = [",".join(columns)]
        for i, row in enumerate(rows):
            cells = ["" if row.get(c) is None else str(row[c]) for c in columns]
            if i == damaged:
                cells = [*cells, "extra"] if rng.random() < 0.5 else cells[: rng.randint(0, len(cells))]
            lines.append(",".join(cells))
        text = "\n".join(lines) + "\n"
        if rng.random() < 0.05:
            text = "\ufeff" + text
        if rng.random() < 0.03:
            text = ""
        path = directory / "data.csv"
    else:
        nested = {"question_id": {"a": 1}, "model": ["m"], "score": [1]}
        lines = [json.dumps(row) for row in rows]
        if damaged >= 0:
            lines[damaged] = rng.choice(["[]", "5", '"x"', "null", json.dumps(nested), "{", "[1,2", "nul"])
        text = "\n".join(lines)
        path = directory / "data.jsonl"
    path.write_text(text, encoding="utf-8")
    return path


def _number() -> list[str]:
    return ["0", "1", "-1", "0.5", "0.05", "1e-9", "1e9", "nan", "inf", "0.8", "0.999", "2", "100"]


def _command(rng: random.Random, path: Path, models: list[str]) -> list[str]:
    odd = ["0.5", "0.9", "0.999", "0.9999999", "0.01", "0", "1", "-1", "2", "nan"]
    confidence = rng.choice(odd) if rng.random() < 0.3 else "0.95"
    command = rng.choice(["summarize", "compare", "leaderboard"] * 2 + ["power"])
    if command == "summarize":
        argv = ["summarize", str(path), "--confidence", confidence]
        argv += ["--ci", rng.choice(["auto", "clt", "wilson", "bootstrap"])]
        if rng.random() < 0.7:
            argv += ["--model", "nope" if rng.random() < 0.05 else rng.choice(models)]
    elif command == "compare":
        argv = ["compare", str(path), "--model-a", rng.choice(models)]
        argv += ["--model-b", "nope" if rng.random() < 0.05 else rng.choice(models)]
        argv += ["--confidence", confidence]
    elif command == "leaderboard":
        alpha = rng.choice(["0.05"] * 12 + ["0.2", "1e-12", "0", "1", "-0.1", "2", "nan"])
        argv = ["leaderboard", str(path), "--confidence", confidence, "--alpha", alpha]
        if rng.random() < 0.3:
            argv += ["--plot", str(path.with_suffix(".svg"))]
    elif rng.random() < 0.5:
        argv = ["power", *rng.choice([["--delta", "0.03"], ["--n", "500"]])]
        argv += rng.choice([["--baseline", "0.7"], ["--variance", "0.2"]])
        argv += rng.choice([
            [], ["--rho", "0.5"], ["--cluster-deff", "2.5"],
            ["--samples-per-question", "4", "--repeat-correlation", "0.5"],
        ])
    else:
        argv = ["power"]
        for flag, chance, values in (
            ("--delta", 0.6, _number()),
            ("--n", 0.5, ["0", "1", "2", "10", "1000", "-5", "100000000"]),
            ("--baseline", 0.6, _number()),
            ("--variance", 0.4, _number()),
            ("--alpha", 0.3, _number()),
            ("--power", 0.3, _number()),
            ("--rho", 0.3, _number()),
            ("--samples-per-question", 0.3, ["0", "1", "3", "-1"]),
            ("--repeat-correlation", 0.3, _number()),
            ("--cluster-deff", 0.3, _number()),
        ):
            if rng.random() < chance:
                argv += [flag, rng.choice(values)]
    return [*argv, "--json"] if rng.random() < 0.85 else argv


def _refuse_constant(name: str) -> float:
    raise AssertionError(f"{name} in JSON output")


def _check(value: Any, where: str = "") -> None:
    """Invariants that hold for every result, whatever the command."""
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check(item, f"{where}[{i}]")
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key.startswith("p_") and isinstance(item, float):
            assert 0.0 <= item <= 1.0, f"{where}.{key} = {item}"
        if key.startswith(("se", "var_")) and isinstance(item, float):
            assert item >= 0.0, f"{where}.{key} = {item}"
        _check(item, f"{where}.{key}")
    if {"ci_low", "ci_high"} <= value.keys():
        assert value["ci_low"] <= value["ci_high"], f"{where}: interval ends are out of order"
    if value.get("method") in ("clt", "wilson"):
        slack = 1e-9 * max(1.0, abs(value["mean"]))
        assert value["ci_low"] - slack <= value["mean"] <= value["ci_high"] + slack, where
    if "entries" in value:
        means = [entry["mean"] for entry in value["entries"]]
        assert means == sorted(means, reverse=True), "leaderboard is not in order of mean"
        for pair in value["pairwise"]:
            used = pair["p_value_clustered"] if pair["p_value_clustered"] is not None else pair["p_value"]
            assert pair["p_holm"] >= used - 1e-12, "a Holm-adjusted p-value below the one it adjusts"


@pytest.mark.parametrize("block", range(8))
def test_any_input_gives_a_result_or_a_one_line_error(tmp_path: Path, block: int) -> None:
    answered = 0
    for seed in range(block * 200, (block + 1) * 200):
        rng = random.Random(seed)
        rows, models = _rows(rng)
        argv = _command(rng, _write(rng, rows, tmp_path), models)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                main(argv)
        except SystemExit as exc:
            message = str(exc.code)
            assert message.startswith("error: "), f"seed {seed}: {argv}: exit {exc.code!r}"
            assert "\n" not in message.strip(), f"seed {seed}: {argv}: {message}"
            continue
        except Exception as exc:  # the failure this test exists to catch
            raise AssertionError(f"seed {seed}: {argv} raised {type(exc).__name__}: {exc}") from exc
        answered += 1
        if "--json" in argv:
            try:
                _check(json.loads(out.getvalue(), parse_constant=_refuse_constant))
            except AssertionError as exc:
                raise AssertionError(f"seed {seed}: {argv}: {exc}") from exc
    assert answered >= 50, "most generated inputs are rejected: the statistics go untested"


def test_check_rejects_what_it_should() -> None:
    with pytest.raises(AssertionError):
        json.loads('{"se": NaN}', parse_constant=_refuse_constant)
    with pytest.raises(AssertionError):
        _check({"p_value": 1.5})
    with pytest.raises(AssertionError):
        _check({"mean": 0.9, "ci_low": 0.1, "ci_high": 0.5, "method": "clt"})
    assert math.isfinite(json.loads('{"se": 0.1}', parse_constant=_refuse_constant)["se"])
