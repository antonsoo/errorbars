"""The vectors the web page's TypeScript is tested against must be the current ones."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


def _exporter() -> Any:
    script = ROOT / "scripts/export_paired_vectors.py"
    spec = importlib.util.spec_from_file_location("export_paired_vectors", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_same(current: Any, committed: Any, where: str) -> None:
    if isinstance(current, dict):
        assert current.keys() == committed.keys(), where
        for key in current:
            _assert_same(current[key], committed[key], f"{where}.{key}")
    elif isinstance(current, list):
        assert len(current) == len(committed), where
        for i, (a, b) in enumerate(zip(current, committed, strict=True)):
            _assert_same(a, b, f"{where}[{i}]")
    elif isinstance(current, float):
        assert current == pytest.approx(committed, rel=1e-12, abs=1e-300), where
    else:
        assert current == committed, where


def test_committed_paired_vectors_match_the_implementation() -> None:
    committed = json.loads((ROOT / "web/paired-vectors.json").read_text())
    _assert_same(_exporter().build(), committed, "vectors")
