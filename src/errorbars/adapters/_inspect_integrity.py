"""Check the recorded cohort and text sample definitions in an Inspect log.

These checks do not establish equivalent graders, model settings or external
sandbox state. Unknown input representations stay unknown instead of becoming
hashes of an ID, a filename or a media URL.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from errorbars.scoring import ScoringRule

if TYPE_CHECKING:
    from inspect_ai.log import EvalLog, EvalSample


def scoring_rule(log: EvalLog, key: str, path: str | Path) -> ScoringRule:
    """Fingerprint the result's recorded scorer parameters, including re-scoring.

    The original eval.scorers declaration may predate `inspect score`. Results
    describe the scores being imported. Epoch reducers and aggregate metrics do
    not change the per-sample grades we read and are deliberately excluded.
    """
    hashes = set()
    assert log.results is not None  # check_complete runs before this function.
    for result in log.results.scores:
        if result.scorer != key or "params" not in result.model_fields_set:
            continue
        try:
            canonical = json.dumps(
                result.params, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(f"{path}: scorer {key!r}: invalid recorded parameters") from exc
        hashes.add("inspect-params-v1:" + hashlib.sha256(canonical.encode("ascii")).hexdigest())
    if len(hashes) > 1:
        raise ValueError(f"{path}: scorer {key!r}: conflicting recorded parameters in Inspect results")
    return ScoringRule("inspect:" + key, next(iter(hashes), None))


def check_complete(log: EvalLog, path: str | Path) -> None:
    if log.status != "success":
        raise ValueError(
            f"{path}: Inspect log status={log.status!r}; cannot analyze an incomplete run. "
            "Finish or retry the evaluation first."
        )
    if log.invalidated:
        raise ValueError(f"{path}: Inspect log contains invalidated samples; resolve them before analysis")
    if not log.samples:
        raise ValueError(f"{path}: log has no samples (status={log.status!r})")
    results = log.results
    if results is None or results.total_samples <= 0:
        raise ValueError(f"{path}: no planned sample count in Inspect results; completeness is unknown")
    actual, planned = len(log.samples), results.total_samples
    logged = getattr(results, "logged_samples", None)
    if actual != planned or results.completed_samples != planned or logged not in (None, planned):
        raise ValueError(
            f"{path}: incomplete Inspect cohort: {actual} recorded, "
            f"{results.completed_samples} completed, {planned} planned samples"
            + (f", logged_samples={logged}" if logged is not None else "")
            + ". Errorbars requires every planned sample; failed, drained or early-stopped "
            "runs cannot be treated as a complete evaluation."
        )
    # Compare to the selected run's total, not the full dataset size: --limit,
    # --sample-id and epochs can legitimately change the number to expect.
    epochs = log.eval.config.epochs if log.eval.config.epochs is not None else 1
    if epochs < 1:
        raise ValueError(f"{path}: invalid planned epoch count {epochs}; expected a positive integer")
    observed: Counter[str] = Counter()
    for sample in log.samples:
        if sample.error is not None or sample.invalidation is not None:
            raise ValueError(
                f"{path}: sample {sample.id!r}, epoch {sample.epoch}: "
                "errored or invalidated, even if a score is present"
            )
        if not 1 <= sample.epoch <= epochs:
            raise ValueError(
                f"{path}: sample {sample.id!r}: epoch {sample.epoch} is outside the planned 1..{epochs}"
            )
        observed[str(sample.id)] += 1
    if any(count != epochs for count in observed.values()):
        raise ValueError(f"{path}: incomplete Inspect cohort: expected {epochs} epochs for every question")
    selected = log.eval.dataset.sample_ids
    if selected is not None and set(observed) != {str(qid) for qid in selected}:
        raise ValueError(f"{path}: recorded question ids differ from Inspect's selected dataset sample_ids")


def question_signature(sample: EvalSample) -> str | None:
    """Exact logged input/choices/target check for self-contained text samples.

Inspect keeps the original dataset input separately from solver messages.
Solver/prompt changes do not alter this signature. Rebuilding the dataset input
does; pairing that experiment requires a separately reviewed identity mapping.
"""
    if sample.files or sample.sandbox or sample.setup:
        return None

    def text(value: str) -> str | None:
        # Resolve only retained local text, without loading media or fetching URLs.
        # A dangling reference cannot establish matching content across two logs.
        if value.startswith(("attachment://", "tc://")):
            value = sample.attachments.get(value.split("://", 1)[1], "")
        if not value.strip() or value.startswith(("attachment://", "tc://")):
            return None
        return value

    if isinstance(sample.input, str):
        source: object = text(sample.input)
        if source is None:
            return None
    else:
        if not sample.input:
            return None
        messages = []
        for message in sample.input:
            # Generated message ids, source annotations and metadata are not
            # question content. Tool histories and multimodal inputs need their
            # own identity policy, rather than a partial text-only signature.
            record = message.model_dump(exclude_none=True)
            if message.role not in ("system", "user", "assistant") or any(
                key not in {"role", "content", "id", "source", "metadata"} for key in record
            ):
                return None
            if isinstance(message.content, str):
                parts = [text(message.content)]
            else:
                parts = []
                for content in message.content:
                    block = content.model_dump(exclude_none=True)
                    if block.get("type") != "text" or set(block) - {"type", "text"}:
                        return None
                    parts.append(text(block["text"]))
            if not parts or any(part is None for part in parts):
                return None
            messages.append({"role": message.role, "content": parts})
        source = messages

    targets = [sample.target] if isinstance(sample.target, str) else sample.target
    target = [text(value) for value in targets]
    choices = [text(value) for value in sample.choices] if sample.choices is not None else None
    if not target or any(value is None for value in target) or (
        choices is not None and any(value is None for value in choices)
    ):
        return None
    canonical = json.dumps(
        {"input": source, "choices": choices, "target": target}, sort_keys=True,
        ensure_ascii=True, separators=(",", ":"), allow_nan=False,
    )
    return "inspect-text-sample-v1:" + hashlib.sha256(canonical.encode("ascii")).hexdigest()
