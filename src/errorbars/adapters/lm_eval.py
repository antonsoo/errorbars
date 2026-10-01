"""Adapter for lm-evaluation-harness `--log_samples` output.

Verified against real output from lm-eval **0.4.13** (the latest stable
release as of 2026-09-24; there is also a 0.5.0.dev1 prerelease with a
different CLI we did not target), generated with:

    lm_eval run --model dummy --tasks copa --limit 20 \\
        --log_samples --output_path <dir>

See ``tests/fixtures/samples_copa_*.jsonl`` (single metric: ``acc``),
``samples_arc_easy_*.jsonl`` (two metrics: ``acc``, ``acc_norm``) and
``samples_gsm8k_cot_self_consistency_*.jsonl`` (three filters) for the exact,
unedited records this adapter is built and tested against.

Each line of a `--log_samples` file is a JSON object with (at least)::

    {"doc_id": 0, "doc": {...}, "target": "...", "arguments": {...},
     "resps": [...], "filtered_resps": [...], "filter": "none",
     "metrics": ["acc"], "acc": 1.0, "doc_hash": "...", ...}

``metrics`` names which top-level keys on the record hold computed scores
(a multiple-choice task can report more than one, e.g. ``acc`` and
``acc_norm``). The samples file has no model name in it (lm-eval's
``--output_path`` subdirectory can be a content hash rather than a model
name, e.g. for the ``dummy`` model used here, which has no identifying
``model_args``), so the caller supplies one.

A task with several filters (``gsm8k_cot_self_consistency`` scores each
question under ``score-first``, ``maj@8`` and ``maj@64``) logs one record per
question *per filter*. Those are three scorings of the same questions, not
three times the questions, so one filter has to be chosen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from errorbars.io import EvalData, _coerce_score

__all__ = ["load_lm_eval_samples"]

# lm-eval's own convention (loggers/evaluation_tracker.py): samples files are
# named "samples_<task>_<ISO timestamp>.jsonl". Searched rather than anchored
# to the start so a path prefix (or a renamed-but-suffixed fixture) still matches.
_TASK_NAME_RE = re.compile(r"samples_(?P<task>.+?)_\d{4}-\d{2}-\d{2}T")


def _infer_task_name(path: Path) -> str | None:
    m = _TASK_NAME_RE.search(path.name)
    return m.group("task") if m else None


def load_lm_eval_samples(
    path: str | Path, model: str, metric: str | None = None, filter_name: str | None = None
) -> EvalData:
    """Load an lm-evaluation-harness ``--log_samples`` JSONL file.

    Args:
        path: path to a ``samples_<task>_<timestamp>.jsonl`` file.
        model: model name to record (lm-eval's samples file doesn't embed
            one usable name for every model type; pass whatever you'd want
            in the ``model`` column).
        metric: which computed metric to use as the score, e.g. ``"acc"``
            or ``"acc_norm"``. Defaults to the first name in each record's
            ``metrics`` list.
        filter_name: which filter's records to use, for a task that scores each
            question under several (e.g. ``"maj@8"``). Required when the
            file holds more than one.

    ``question_id`` is the task name (inferred from the filename, if it
    matches lm-eval's naming convention) plus ``doc_id``, e.g.
    ``"copa-3"``, so files from different tasks can be safely concatenated.
    """
    path = Path(path)
    task_name = _infer_task_name(path)

    records: list[tuple[int, dict[str, object]]] = []
    filters: dict[str, None] = {}  # in order of first appearance
    with open(path, encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(rec, dict):
                raise ValueError(
                    f"{path}:{lineno}: expected a JSON object per line, got {type(rec).__name__}"
                )
            records.append((lineno, rec))
            filters.setdefault(str(rec.get("filter", "none")))

    if not records:
        raise ValueError(f"{path}: no records found")
    if filter_name is None and len(filters) > 1:
        raise ValueError(
            f"{path}: the task scores each question under {len(filters)} filters "
            f"({', '.join(filters)}); pick one with filter_name=... (--filter on the command line)"
        )
    if filter_name is not None and filter_name not in filters:
        raise ValueError(f"{path}: no records for filter {filter_name!r} (has: {', '.join(filters)})")

    question_id: list[str] = []
    model_col: list[str] = []
    score: list[float] = []
    first_line: dict[str, int] = {}

    for lineno, rec in records:
        if filter_name is not None and str(rec.get("filter", "none")) != filter_name:
            continue
        metrics = rec.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            raise ValueError(f"{path}:{lineno}: record has no non-empty 'metrics' list")
        key = metric or str(metrics[0])
        if key not in rec:
            raise ValueError(
                f"{path}:{lineno}: metric {key!r} not present on this record (available: {metrics})"
            )

        qid = str(rec.get("doc_id", lineno - 1))
        if task_name:
            qid = f"{task_name}-{qid}"
        # The same question twice would count as two questions and shrink every standard error.
        if qid in first_line:
            raise ValueError(
                f"{path}:{lineno}: a second record for doc_id {rec.get('doc_id')!r} "
                f"(first on line {first_line[qid]})"
            )
        first_line[qid] = lineno
        question_id.append(qid)
        model_col.append(model)
        try:
            score.append(_coerce_score(rec[key], lineno))
        except ValueError as exc:
            raise ValueError(f"{path}: metric {key!r}, {str(exc).replace('row', 'line', 1)}") from exc

    return EvalData(question_id=question_id, model=model_col, score=score)
