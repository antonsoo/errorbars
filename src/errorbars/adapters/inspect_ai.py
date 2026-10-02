"""Adapter for Inspect AI eval logs.

Verified against a real log produced by **inspect-ai 0.3.268**, running a
5-sample task through the built-in ``mockllm/model`` provider (no network
model calls). See ``tests/fixtures/inspect_tiny_qa.eval`` for the exact,
unedited log this adapter is built and tested against.

This reads logs with Inspect's own ``inspect_ai.log.read_eval_log`` and
converts score values with its own ``inspect_ai.scorer.value_to_float``
(the same conversion Inspect uses for its own metrics: correct/incorrect/
partial/no-answer string codes -> 1.0/0.0/0.5/0.0, numbers and bools pass
through) rather than hand-parsing the ``.eval`` file, which is a versioned
binary/zip format not meant to be read directly. Requires the ``inspect``
extra: ``pip install "errorbars[inspect]"``.
"""

from __future__ import annotations

import math
from pathlib import Path

from errorbars.io import EvalData

__all__ = ["load_inspect_log"]


def load_inspect_log(path: str | Path, scorer: str | None = None) -> EvalData:
    """Load per-sample scores from an Inspect AI ``.eval`` or ``.json`` log.

    Args:
        path: path to the log file (as written by ``inspect eval``).
        scorer: which scorer's score to use, for tasks with more than one
            scorer. Defaults to the only scorer, and raises if a sample has
            more than one and none was specified.

    Repeated ``--epochs`` sampling of the same input is captured in the
    ``sample`` column (Inspect's per-sample ``epoch`` number), so
    ``errorbars summarize`` can decompose within/between-question variance.
    """
    try:
        from inspect_ai.log import read_eval_log
        from inspect_ai.scorer import value_to_float
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "reading an Inspect log needs inspect-ai, which the 'inspect' extra installs: "
            'pip install "errorbars[inspect]"'
        ) from exc

    try:
        log = read_eval_log(str(path))
    except OSError:
        raise
    except Exception as exc:
        # Inspect reports a file it can't parse in its own terms ("EOCD not found", a list of
        # missing fields); say which file, and that the problem is its format.
        reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise ValueError(f"{path}: not a log Inspect can read ({reason})") from exc
    if not log.samples:
        raise ValueError(f"{path}: log has no samples (status={log.status!r})")

    model = str(log.eval.model)
    to_float = value_to_float()

    question_id: list[str] = []
    model_col: list[str] = []
    score: list[float] = []
    sample_col: list[str] = []

    for s in log.samples:
        if not s.scores:
            continue
        if scorer is not None:
            if scorer not in s.scores:
                raise ValueError(
                    f"{path}: sample {s.id!r} has no scorer {scorer!r} (has: {list(s.scores)})"
                )
            key = scorer
        elif len(s.scores) == 1:
            key = next(iter(s.scores))
        else:
            raise ValueError(
                f"{path}: sample {s.id!r} has multiple scorers {list(s.scores)}; "
                "pass `scorer=...` to pick one"
            )
        value = s.scores[key].value
        # value_to_float turns anything it can't read into 0.0. A scorer with several named
        # values has no single score to read, so say so instead of reporting a mean of 0.
        if isinstance(value, (dict, list)):
            raise ValueError(
                f"{path}: sample {s.id!r}: scorer {key!r} returns {type(value).__name__} values "
                f"({value!r}), not one score per sample"
            )
        number = float(to_float(value))
        if not math.isfinite(number):
            raise ValueError(f"{path}: sample {s.id!r}: score {value!r} is not a finite number")
        question_id.append(str(s.id))
        model_col.append(model)
        score.append(number)
        sample_col.append(str(s.epoch))

    if not question_id:
        raise ValueError(f"{path}: no scored samples found")

    return EvalData(question_id=question_id, model=model_col, score=score, sample=sample_col)
