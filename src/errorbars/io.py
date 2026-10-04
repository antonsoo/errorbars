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
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from numbers import Real
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
        self.validate()
        if len(self.models()) > 1:
            raise ValueError("select one model before averaging scores by question")
        totals: dict[str, list[float]] = {}
        for qid, s in zip(self.question_id, self.score, strict=True):
            totals.setdefault(qid, []).append(s)
        return {qid: sum(v) / len(v) for qid, v in totals.items()}

    def cluster_by_question(self) -> dict[str, str]:
        if not self.cluster_id:
            return {}
        out: dict[str, str] = {}
        for qid, c in zip(self.question_id, self.cluster_id, strict=True):
            if qid in out and out[qid] != c:
                raise ValueError(f"question {qid!r}: conflicting cluster assignments {out[qid]!r} and {c!r}")
            out[qid] = c
        return out

    def validate(self) -> None:
        """Validate normalized rows, including adapter and directly constructed datasets."""
        n = len(self)
        fields = {
            "question_id": self.question_id,
            "model": self.model,
            "cluster_id": self.cluster_id,
            "sample": self.sample,
        }
        for name, values in fields.items():
            if values is None:
                if name in ("question_id", "model"):
                    raise ValueError(f"{name} must have one identifier per score")
                continue
            if len(values) != n:
                raise ValueError(f"{name} must have one identifier per score")
            for row, value in enumerate(values, 1):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"row {row}: {name} must be a nonempty string identifier")
        for row, score in enumerate(self.score, 1):
            if not isinstance(score, Real):
                raise ValueError(f"row {row}: normalized score must be numeric")
            _coerce_score(score, row)
        seen: dict[tuple[str, str, str], int] = {}
        for row, (model, qid, sample) in enumerate(
            zip(self.model, self.question_id, self.sample or ["0"] * n, strict=True), 1
        ):
            key = (model, qid, sample)
            if key in seen:
                raise ValueError(
                    f"row {row}: already has a score for model {model!r}, question {qid!r}, "
                    f"sample {sample!r} (row {seen[key]})"
                )
            seen[key] = row
        self.cluster_by_question()


def concat(parts: Iterable[tuple[str, EvalData]]) -> EvalData:
    """Put several sources' rows together: one log per model, or one per task.

    ``parts`` pairs each source's name (a path, used in error messages) with its data. A
    Missing cluster metadata is resolved only from another source's assignment for the
    same question. A question without such an assignment is an error when combining
    clustered sources. A missing sample column defaults to sample ``"0"``.

    The same (model, question, sample) in two sources is an error, as it is within one file:
    counted twice, it would inflate n and shrink every standard error. It happens when a run
    is given twice, or when two runs of one model are given without telling them apart.
    """
    parts = list(parts)
    if not parts:
        raise ValueError("no data to combine")
    cluster_map: dict[str, str] = {}
    cluster_source: dict[str, str] = {}
    for source, data in parts:
        try:
            data.validate()
        except ValueError as exc:
            raise ValueError(f"{source}: {exc}") from exc
        for qid, cluster in data.cluster_by_question().items():
            if qid in cluster_map and cluster_map[qid] != cluster:
                raise ValueError(
                    f"{source}: question {qid!r}: conflicting cluster assignments "
                    f"{cluster_map[qid]!r} (from {cluster_source[qid]}) and {cluster!r}"
                )
            cluster_map[qid] = cluster
            cluster_source[qid] = source
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
        if any_clusters:
            for qid in data.question_id:
                if qid not in cluster_map:
                    raise ValueError(
                        f"{source}: no cluster assignment for question {qid!r}; "
                        "supply cluster metadata for every question"
                    )
                cluster_id.append(cluster_map[qid])
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
    except (TypeError, ValueError, OverflowError) as exc:
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
    if value is None:
        raise ValueError(f"row {n}: no value for column '{column}'")
    return _identifier(value, column, n)


def _identifier(value: Any, column: str, row: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"row {row}: {column!r} must be a nonempty scalar identifier")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"row {row}: {column!r} must be a finite identifier")
    label = str(value)
    if not label.strip():
        raise ValueError(f"row {row}: {column!r} must be a nonempty identifier")
    return label


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"duplicate JSON field {key!r}")
        record[key] = value
    return record


def _names(row: dict[str, Any]) -> str:
    """A row's field names for an error message: the first ten, each cut to a readable length."""
    names = [str(name) for name in row]
    shown = [name if len(name) <= 40 else name[:39] + "\u2026" for name in names[:10]]
    more = f", and {len(names) - 10} more" if len(names) > 10 else ""
    return (", ".join(shown) + more) or "no fields"


def _from_records(records: Iterable[dict[str, Any]], columns: ColumnMap) -> EvalData:
    question_id: list[str] = []
    model: list[str] = []
    score: list[float] = []
    cluster_map: dict[str, str] = {}
    sample: list[str] = []
    has_samples = False

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
        for required in (columns.question_id, columns.model, columns.score):
            if required not in row:
                raise ValueError(f"missing required column '{required}' in row {n} (it has: {_names(row)})")
        question_id.append(_label(row, columns.question_id, n))
        model.append(_label(row, columns.model, n))
        score.append(_coerce_score(row[columns.score], n))
        if columns.cluster_id is not None and columns.cluster_id in row:
            cluster = _identifier(row[columns.cluster_id], columns.cluster_id, n)
            qid = question_id[-1]
            if qid in cluster_map and cluster_map[qid] != cluster:
                raise ValueError(
                    f"row {n}: question {qid!r}: conflicting cluster assignments "
                    f"{cluster_map[qid]!r} and {cluster!r}"
                )
            cluster_map[qid] = cluster
        sample_id = "0"
        if columns.sample is not None and columns.sample in row:
            has_samples = True
            sample_id = _identifier(row[columns.sample], columns.sample, n)
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

    cluster_id = None
    if cluster_map:
        for row_number, qid in enumerate(question_id, 1):
            if qid not in cluster_map:
                raise ValueError(
                    f"row {row_number}: no cluster assignment for question {qid!r}; "
                    "supply cluster metadata for every question"
                )
        cluster_id = [cluster_map[qid] for qid in question_id]
    return EvalData(question_id, model, score, cluster_id, sample if has_samples else None, columns)


def _delimiter(header: str, columns: ColumnMap) -> str:
    """The delimiter the header was written with.

    A spreadsheet saves "CSV" with the list separator of its locale: a semicolon wherever the
    decimal mark is a comma (most of Europe), sometimes a tab. The header settles it: the
    delimiter is the one that splits it into the columns being looked for.
    """
    wanted = {columns.question_id, columns.model, columns.score}
    for delimiter in (",", ";", "\t"):
        names = {name.strip() for name in next(csv.reader([header], delimiter=delimiter), [])}
        if wanted <= names:
            return delimiter
    return ","


_DECIMAL_COMMA = re.compile(r"[+-]?\d+,\d+(?:[eE][+-]?\d+)?")


def _decimal_commas(records: Iterable[dict[str, Any]], score: str) -> Iterable[dict[str, Any]]:
    """Scores written ``0,75`` in a file whose delimiter is not the comma."""
    for row in records:
        value = row.get(score)
        if isinstance(value, str) and _DECIMAL_COMMA.fullmatch(value.strip()):
            row[score] = value.strip().replace(",", ".")
        yield row


def load_csv(path: str | Path, columns: ColumnMap | None = None) -> EvalData:
    """Load per-item scores from a CSV file.

    Read as a spreadsheet writes it too: with a byte-order mark ("CSV UTF-8" in Excel), with
    semicolons or tabs between the fields, and with decimal commas when the delimiter is not
    the comma.
    """
    columns = columns or ColumnMap()
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = f.readline()
        f.seek(0)
        delimiter = _delimiter(header, columns)
        reader = csv.DictReader(f, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty or headerless CSV")
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        seen_headers: set[str] = set()
        for name in reader.fieldnames:
            if name in seen_headers:
                raise ValueError(f"{path}: duplicate CSV column {name!r}")
            seen_headers.add(name)
        records: Iterable[dict[str, Any]] = reader
        if delimiter != ",":
            records = _decimal_commas(reader, columns.score)
        return _from_records(records, columns)


def load_jsonl(path: str | Path, columns: ColumnMap | None = None) -> EvalData:
    """Load per-item scores from a JSON Lines file (one record per line)."""
    columns = columns or ColumnMap()
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line, object_pairs_hook=_unique_fields)
            except ValueError as exc:
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
