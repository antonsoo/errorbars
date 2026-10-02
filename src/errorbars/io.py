"""Loading per-item eval scores from CSV, JSONL, or a pandas DataFrame.

The canonical shape is "long format": one row per (question, model[, sample])
with columns ``question_id``, ``model``, ``score``, and optional
``cluster_id`` / ``sample``. Column names are configurable so you don't have
to reshape your existing logs.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "EvalData",
    "ColumnMap",
    "concat",
    "load_csv",
    "load_jsonl",
    "load_dataframe",
    "write_csv",
]


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


def concat(parts: Iterable[tuple[str, EvalData]]) -> EvalData:
    """Put several sources' rows together: one log per model, or one per task.

    ``parts`` pairs each source's name (a path, used in error messages) with its data. A
    source without cluster ids or sample ids gets what a file without those columns gets:
    each question its own cluster, sample ``"0"``.

    The same (model, question, sample) in two sources is an error, as it is within one file:
    counted twice, it would inflate n and shrink every standard error. It happens when a run
    is given twice, or when two runs of one model are given without telling them apart.
    """
    parts = list(parts)
    if not parts:
        raise ValueError("no data to combine")
    if len(parts) == 1:
        return parts[0][1]
    any_clusters = any(data.cluster_id for _, data in parts)
    any_samples = any(data.sample for _, data in parts)

    question_id: list[str] = []
    model: list[str] = []
    score: list[float] = []
    cluster_id: list[str] = []
    sample: list[str] = []
    seen: dict[tuple[str, str, str], str] = {}
    for source, data in parts:
        samples = data.sample or ["0"] * len(data)
        for m, q, smp in zip(data.model, data.question_id, samples, strict=True):
            key = (m, q, smp)
            if key in seen:
                raise ValueError(
                    f"{source}: model {m!r} already has a score for question {q!r} (from "
                    f"{seen[key]}). Either the same run is given twice, or these are two runs "
                    "of one model, which need different model names (NAME=PATH names a "
                    "harness log's model)"
                )
            seen[key] = source
        question_id.extend(data.question_id)
        model.extend(data.model)
        score.extend(data.score)
        cluster_id.extend(data.cluster_id or data.question_id)
        sample.extend(samples)

    return EvalData(
        question_id,
        model,
        score,
        cluster_id if any_clusters else None,
        sample if any_samples else None,
        parts[0][1].columns,
    )


_MAX_SCORE = 1e100


def _coerce_score(raw: Any, row: int) -> float:
    if isinstance(raw, bool):
        return float(raw)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row}: could not parse score value {raw!r} as a number") from exc
    # A NaN would propagate into every mean, CI and p-value (and sort to the top of a leaderboard);
    # a missing or failed grade has to be decided on explicitly, not averaged in as "not a number".
    if not math.isfinite(value):
        raise ValueError(f"row {row}: score {raw!r} is not a finite number")
    # Variances square the scores: beyond this they overflow to infinity.
    if abs(value) > _MAX_SCORE:
        raise ValueError(f"row {row}: score {raw!r} is too large to analyze (limit {_MAX_SCORE:g})")
    return value


def _label(row: Any, column: str, n: int) -> str:
    value = row[column]
    # csv.DictReader fills the cells a short row lacks with None.
    if value is None:
        raise ValueError(f"row {n}: no value for column '{column}' (the row has too few fields)")
    return str(value)


def _from_records(records: Iterable[dict[str, Any]], columns: ColumnMap) -> EvalData:
    question_id: list[str] = []
    model: list[str] = []
    score: list[float] = []
    cluster_id: list[str] | None = [] if columns.cluster_id else None
    sample: list[str] | None = [] if columns.sample else None

    n = 0
    seen: dict[tuple[str, str, str], int] = {}
    for row in records:
        n += 1
        if not isinstance(row, dict):
            raise ValueError(f"row {n}: expected a record with named fields, got {type(row).__name__}")
        # csv.DictReader collects the cells beyond the header under the key None.
        if None in row:
            raise ValueError(
                f"row {n}: more fields than the header has columns (an unquoted comma in a value?)"
            )
        if columns.question_id not in row:
            raise ValueError(f"missing required column '{columns.question_id}' in row {n}")
        if columns.model not in row:
            raise ValueError(f"missing required column '{columns.model}' in row {n}")
        if columns.score not in row:
            raise ValueError(f"missing required column '{columns.score}' in row {n}")
        question_id.append(_label(row, columns.question_id, n))
        model.append(_label(row, columns.model, n))
        score.append(_coerce_score(row[columns.score], n))
        if cluster_id is not None and columns.cluster_id is not None:
            cluster_id.append(str(row.get(columns.cluster_id, question_id[-1])))
        sample_id = str(row.get(columns.sample, "0")) if columns.sample is not None else "0"
        if sample is not None:
            sample.append(sample_id)
        # The same (model, question, sample) twice would be counted as two questions, inflating n and
        # shrinking every standard error. Repeated generations need distinct sample ids.
        key = (model[-1], question_id[-1], sample_id)
        if key in seen:
            raise ValueError(
                f"row {n}: model {key[0]!r} already has a score for question {key[1]!r} (row {seen[key]}); "
                f"give repeated generations distinct values in a '{columns.sample or 'sample'}' column"
            )
        seen[key] = n

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
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"{path}:{lineno}: expected a JSON object per line, got {type(record).__name__}"
                )
            records.append(record)
    if not records:
        raise ValueError(f"{path}: no records found")
    return _from_records(records, columns)


def load_dataframe(df: Any, columns: ColumnMap | None = None) -> EvalData:
    """Load per-item scores from a pandas DataFrame."""
    columns = columns or ColumnMap()
    records = df.to_dict(orient="records")
    return _from_records(records, columns)


def write_csv(data: EvalData, path: str | Path) -> None:
    """Write an ``EvalData`` back out as a canonical long-format CSV.

    Used by ``errorbars import`` to turn an adapter's output into a file
    ``summarize``/``compare``/``leaderboard`` can load directly. Only
    includes ``cluster_id`` / ``sample`` columns when the data actually has
    them.
    """
    fieldnames = ["question_id", "model", "score"]
    if data.cluster_id:
        fieldnames.append("cluster_id")
    if data.sample:
        fieldnames.append("sample")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i in range(len(data)):
            row: dict[str, Any] = {
                "question_id": data.question_id[i],
                "model": data.model[i],
                "score": data.score[i],
            }
            if data.cluster_id:
                row["cluster_id"] = data.cluster_id[i]
            if data.sample:
                row["sample"] = data.sample[i]
            writer.writerow(row)
