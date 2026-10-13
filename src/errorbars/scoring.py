"""Recorded scoring declarations, separate from question content and model output.

Equal declarations do not establish equal scorer implementations or external
grader state. Missing configuration is unknown, even when the scorer name agrees.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringRule:
    """Recorded scorer, configuration fingerprint and optional selected dictionary key.

    A missing value_key denotes the whole scalar score for a known scorer.
    A selected key remains significant even when configuration is unknown.
    """

    name: str
    config_hash: str | None = None
    value_key: str | None = None

    def conflicts_with(self, other: ScoringRule) -> bool:
        return self.name != other.name or self.value_key != other.value_key or (
            self.config_hash is not None and other.config_hash is not None
            and self.config_hash != other.config_hash
        )


def score_value_labels(rules: Iterable[tuple[str, ScoringRule | None]]) -> list[dict[str, str | None]]:
    """Label selected dimensions without exposing scorer parameter values."""
    labels = dict.fromkeys(
        (model, rule.name, rule.value_key) for model, rule in rules if rule is not None
    )
    if not any(key is not None for _, _, key in labels):
        return []
    return [{"model": model, "scorer": scorer, "scorer_value": key} for model, scorer, key in labels]


def compare_scoring(
    left: Mapping[str, tuple[ScoringRule | None, bool]],
    right: Mapping[str, tuple[ScoringRule | None, bool]],
) -> dict[str, str]:
    """Compare per-question declarations and their completeness on shared ids."""
    states = {}
    for question in sorted(left.keys() & right.keys()):
        a, a_complete = left[question]
        b, b_complete = right[question]
        if a is not None and b is not None and a.conflicts_with(b):
            states[question] = "conflicting"
        elif a_complete and b_complete:
            states[question] = "matching"
        else:
            states[question] = "unavailable"
    return states
