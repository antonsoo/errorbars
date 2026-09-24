"""Loading per-item eval scores from CSV, JSONL, or a pandas DataFrame.

The canonical shape is "long format": one row per (question, model[, sample])
with columns ``question_id``, ``model``, ``score``, and optional
``cluster_id`` / ``sample``. Column names are configurable so you don't have
to reshape your existing logs.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["EvalData", "ColumnMap", "load_csv", "load_jsonl", "load_dataframe"]


@dataclass(frozen=True)
class ColumnMap:
    """Names of the columns in your source data, if not the defaults."""

    question_id: str = "question_id"
    model: str = "model"
    score: str = "score"
    cluster_id: str | None = "cluster_id"
    sample: str | None = "sample"


@dataclass
class EvalData:
    """Normalized long-format eval records, one row per observation."""

    question_id: list[str]
    model: list[str]
    score: list[float]
    cluster_id: list[str] | None = None
    sample: list[str] | None = None
    columns: ColumnMap = field(default_factory=ColumnMap)

    def __len__(self) -> int:
        return len(self.score)

    def models(self) -> list[str]:
        seen: dict[str, None] = {}
        for m in self.model:
            seen.setdefault(m, None)
        return list(seen)

    def filter_model(self, model: str) -> EvalData:
        idx = [i for i, m in enumerate(self.model) if m == model]
        return EvalData(
            question_id=[self.question_id[i] for i in idx],
            model=[self.model[i] for i in idx],
            score=[self.score[i] for i in idx],
            cluster_id=[self.cluster_id[i] for i in idx] if self.cluster_id else None,
            sample=[self.sample[i] for i in idx] if self.sample else None,
            columns=self.columns,
        )

    def scores_by_question(self) -> dict[str, float]:
        """Mean score per question_id (collapses repeated samples)."""
        totals: dict[str, list[float]] = {}
        for qid, s in zip(self.question_id, self.score, strict=True):
            totals.setdefault(qid, []).append(s)
        return {qid: sum(v) / len(v) for qid, v in totals.items()}

    def cluster_by_question(self) -> dict[str, str]:
        if not self.cluster_id:
            return {}
        out: dict[str, str] = {}
        for qid, c in zip(self.question_id, self.cluster_id, strict=True):
            out.setdefault(qid, c)
        return out


def _coerce_score(raw: Any) -> float:
    if isinstance(raw, bool):
        return float(raw)
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"could not parse score value {raw!r} as a number") from exc


def _from_records(records: Iterable[dict[str, Any]], columns: ColumnMap) -> EvalData:
    question_id: list[str] = []
    model: list[str] = []
    score: list[float] = []
    cluster_id: list[str] | None = [] if columns.cluster_id else None
    sample: list[str] | None = [] if columns.sample else None

    n = 0
    for row in records:
        n += 1
        if columns.question_id not in row:
            raise ValueError(f"missing required column '{columns.question_id}' in row {n}")
        if columns.model not in row:
            raise ValueError(f"missing required column '{columns.model}' in row {n}")
        if columns.score not in row:
            raise ValueError(f"missing required column '{columns.score}' in row {n}")
        question_id.append(str(row[columns.question_id]))
        model.append(str(row[columns.model]))
        score.append(_coerce_score(row[columns.score]))
        if cluster_id is not None and columns.cluster_id is not None:
            cluster_id.append(str(row.get(columns.cluster_id, question_id[-1])))
        if sample is not None and columns.sample is not None:
            sample.append(str(row.get(columns.sample, "0")))

    if n == 0:
        raise ValueError("no rows found in input data")

    return EvalData(question_id, model, score, cluster_id, sample, columns)


def load_csv(path: str | Path, columns: ColumnMap | None = None) -> EvalData:
    """Load per-item scores from a CSV file."""
    columns = columns or ColumnMap()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty or headerless CSV")
        return _from_records(reader, columns)


def load_jsonl(path: str | Path, columns: ColumnMap | None = None) -> EvalData:
    """Load per-item scores from a JSON Lines file (one record per line)."""
    columns = columns or ColumnMap()
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    if not records:
        raise ValueError(f"{path}: no records found")
    return _from_records(records, columns)


def load_dataframe(df: Any, columns: ColumnMap | None = None) -> EvalData:
    """Load per-item scores from a pandas DataFrame."""
    columns = columns or ColumnMap()
    records = df.to_dict(orient="records")
    return _from_records(records, columns)
