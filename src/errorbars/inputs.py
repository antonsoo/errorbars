"""Reading results the way they are left on disk: several files, in several formats.

An eval harness writes one log per model and per task. lm-evaluation-harness puts
``samples_<task>_<timestamp>.jsonl`` files in a directory per model; Inspect AI writes one
``.eval`` log per run. Comparing two models therefore starts from two files at least, and
the question this package answers is always about more than one of them. :func:`load_inputs`
takes them as they are:

- a CSV or JSONL file in errorbars' own long format;
- an lm-eval samples file, recognized by its records;
- an Inspect ``.eval`` (or ``.json``) log;
- a directory, searched for lm-eval samples files and Inspect logs.

and returns their rows as one :class:`~errorbars.io.EvalData`.

A harness log can be given as ``NAME=PATH`` to name its model: to tell two runs of one
model apart (``greedy=run1.eval sampled=run2.eval``), or because an lm-eval samples file
that was moved away from its ``results_*.json`` no longer says which model wrote it.
"""

from __future__ import annotations

import errno
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from errorbars.adapters.lm_eval import (
    load_lm_eval_samples,
    looks_like_samples,
    samples_file_parts,
)
from errorbars.io import ColumnMap, EvalData, concat, load_csv, load_jsonl

__all__ = ["Loaded", "load_inputs", "split_spec"]


@dataclass
class Loaded:
    """What :func:`load_inputs` read, and what it chose not to."""

    data: EvalData
    #: The files the rows came from, in the order they were read.
    files: list[Path] = field(default_factory=list)
    #: Things the caller should tell the user: an older run that was passed over.
    notes: list[str] = field(default_factory=list)


def split_spec(spec: str) -> tuple[str | None, Path]:
    """``NAME=PATH`` as ``(NAME, PATH)``, or a plain path as ``(None, PATH)``.

    A path that exists is a path, whatever characters it holds, so a file name with ``=`` in
    it is never cut in two.
    """
    if os.path.exists(spec):
        return None, Path(spec)
    name, sep, rest = spec.partition("=")
    if sep and name and os.path.exists(rest):
        return name, Path(rest)
    raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), spec)


def _first_record(path: Path) -> object:
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    return None
    return None


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in (".eval", ".json"):
        return "inspect"
    if suffix in (".jsonl", ".ndjson"):
        return "lm-eval" if looks_like_samples(_first_record(path)) else "jsonl"
    raise ValueError(
        f"{path}: unrecognized file extension {path.suffix!r} "
        "(use .csv or .jsonl, an lm-eval samples_*.jsonl, or an Inspect .eval log)"
    )


def _expand_directory(directory: Path, notes: list[str]) -> list[Path]:
    """The logs under a directory: every Inspect log, and the latest lm-eval samples file
    per task in each sub-directory (lm-eval adds a timestamped file on every re-run)."""
    samples = sorted(directory.rglob("samples_*.jsonl"))
    logs = sorted(directory.rglob("*.eval"))
    if not samples and not logs:
        raise ValueError(
            f"{directory}: no lm-eval samples_*.jsonl files or Inspect .eval logs in this directory"
        )
    latest: dict[tuple[Path, str], Path] = {}
    runs: dict[tuple[Path, str], int] = {}
    for path in samples:
        parts = samples_file_parts(path)
        key = (path.parent, parts[0] if parts else path.name)
        runs[key] = runs.get(key, 0) + 1
        # ISO timestamps sort as text; `samples` is sorted, so the last one seen is the latest.
        latest[key] = path
    for key, count in runs.items():
        if count > 1:
            notes.append(
                f"{key[0]}: {count} runs of {key[1]}; using the latest ({latest[key].name})"
            )
    return sorted(latest.values()) + logs


def _load_one(
    path: Path,
    name: str | None,
    model: str | None,
    columns: ColumnMap,
    metric: str | None,
    filter_name: str | None,
    scorer: str | None,
) -> EvalData:
    """One file. ``name`` is the NAME of a NAME=PATH given for it; ``model`` the name given
    for every harness log."""
    kind = _kind(path)
    if kind in ("csv", "jsonl"):
        if name is not None:
            raise ValueError(
                f"{path}: this file names its models in its {columns.model!r} column; "
                f"NAME=PATH ({name}=...) is for a harness log, which holds one model"
            )
        return load_csv(path, columns) if kind == "csv" else load_jsonl(path, columns)
    if kind == "lm-eval":
        return load_lm_eval_samples(
            path, model=name or model, metric=metric, filter_name=filter_name
        )

    from errorbars.adapters.inspect_ai import load_inspect_log

    data = load_inspect_log(path, scorer=scorer)
    if name or model:
        data.model = [str(name or model)] * len(data)
    return data


def load_inputs(
    specs: Sequence[str | Path],
    columns: ColumnMap | None = None,
    *,
    model: str | None = None,
    metric: str | None = None,
    filter_name: str | None = None,
    scorer: str | None = None,
) -> Loaded:
    """Load one or more files or directories (each optionally as ``NAME=PATH``) as one dataset.

    Args:
        specs: paths, or ``NAME=PATH`` strings naming a harness log's model.
        columns: column names, for files in errorbars' own format.
        model: a model name for every harness log that isn't given one as ``NAME=PATH``.
        metric: lm-eval metric to use as the score (default: each record's first).
        filter_name: lm-eval filter to use, for a task scored under several.
        scorer: Inspect scorer to use, for a task with more than one.
    """
    columns = columns or ColumnMap()
    if not specs:
        raise ValueError("no input files given")
    notes: list[str] = []
    files: list[Path] = []
    parts: list[tuple[str, EvalData]] = []
    for spec in specs:
        name, path = split_spec(str(spec))
        paths = _expand_directory(path, notes) if path.is_dir() else [path]
        for one in paths:
            data = _load_one(one, name, model, columns, metric, filter_name, scorer)
            files.append(one)
            parts.append((str(one), data))
    return Loaded(data=concat(parts), files=files, notes=notes)
