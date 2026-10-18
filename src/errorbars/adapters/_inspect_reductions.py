"""Import recorded question reductions without executing reducer functions.

Inspect's max/pass-at-k/etc. scores are different observations from the mean of
its raw epochs. Read the retained values, checking their cohort and linking each
score to the correct array in the native log. Ordinary means retain raw epochs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from errorbars.io import EvalData, RecordSource, _identifier
from errorbars.scoring import ScoringRule

if TYPE_CHECKING:
    from inspect_ai.log import EvalLog
    from inspect_ai.scorer import Value


def select_reducer(
    log: EvalLog, scorer: str, path: str | Path, value_key: str | None,
    requested: str | None,
) -> str:
    """Select the scored view, preferring results over stale eval configuration."""
    assert log.results is not None
    choices = {
        result.reducer or "mean" for result in log.results.scores
        if result.scorer == scorer and (value_key is None or result.name == value_key)
    }
    if not choices:
        # Old/partial result metadata must not hide a known non-mean declaration.
        choices = set(log.eval.config.epochs_reducer or ["mean"])
    if requested is not None:
        if requested not in choices:
            raise ValueError(
                f"{path}: scorer {scorer!r}: epoch reducer {requested!r} is not recorded "
                f"(available: {sorted(choices)}); --inspect-reducer selects a recorded view"
            )
        return requested
    if len(choices) != 1:
        raise ValueError(
            f"{path}: scorer {scorer!r}: multiple epoch reducers {sorted(choices)}; "
            "select one with inspect_reducer=... (--inspect-reducer)"
        )
    return next(iter(choices))


def recorded_reduction(
    log: EvalLog, raw: EvalData, scorer: str, reducer: str, path: str | Path,
    numeric_grade: Callable[[Value, object], float],
) -> EvalData:
    """One scalar per original question from exactly one complete native view.

The raw data is already validated, including content/scoring conflicts between
epochs. A partial or duplicate reduction is never interpreted as a new cohort.
"""
    views = [
        (index, view) for index, view in enumerate(log.reductions or [])
        if view.scorer == scorer and view.reducer == reducer
    ]
    if len(views) != 1:
        raise ValueError(
            f"{path}: scorer {scorer!r}: expected one recorded {reducer!r} reduction, "
            f"found {len(views)}; cannot reconstruct it from raw epochs"
        )
    index, view = views[0]
    original: dict[str, list[int]] = {}
    for i, question in enumerate(raw.question_id):
        original.setdefault(question, []).append(i)
    assert raw.scoring is not None and raw.scoring[0] is not None
    rule = raw.scoring[0]
    epochs = log.eval.config.epochs or 1
    # The reducer and attempt budget are part of the observation's definition.
    # Parameters/implementations absent from the log remain unverified, just as
    # with native scorer declarations; no arbitrary callable is imported here.
    reduced_rule = ScoringRule(
        f"{rule.name} [epoch reducer={reducer}; epochs={epochs}]",
        rule.config_hash, rule.value_key,
    )
    questions: list[str] = []
    scores: list[float] = []
    signatures: list[str | None] = []
    sources: list[RecordSource | None] = []
    for record, sample in enumerate(view.samples, 1):
        question = _identifier(sample.sample_id, "reduced sample_id", record)
        if question not in original:
            raise ValueError(f"{path}: {reducer!r} reduction has unknown question {question!r}")
        questions.append(question)
        scores.append(numeric_grade(sample.value, question))
        indices = original[question]
        hashes = [raw.question_hash[i] if raw.question_hash else None for i in indices]
        signatures.append(hashes[0] if all(hashes) else None)
        sources.append(RecordSource(
            str(path), record,
            metric=f"{scorer} [epoch reducer={reducer}; reductions[{index}].samples]",
        ))
    if len(questions) != len(set(questions)) or set(questions) != set(original):
        raise ValueError(
            f"{path}: {reducer!r} reduction must retain every original question exactly once "
            "(missing or duplicate reduced scores)"
        )
    data = EvalData(
        question_id=questions, model=[raw.model[0]] * len(questions), score=scores,
        sources=sources, question_hash=signatures if any(signatures) else None,
        scoring=[reduced_rule] * len(questions),
    )
    data.validate()
    return data
