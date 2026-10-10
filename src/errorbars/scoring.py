"""Recorded scoring declarations, separate from question content and model output.

Equal declarations do not establish equal scorer implementations or external
grader state. Missing configuration is unknown, even when the scorer name agrees.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringRule:
    """A namespaced scorer name and, when recorded, its configuration fingerprint."""

    name: str
    config_hash: str | None = None

    def conflicts_with(self, other: ScoringRule) -> bool:
        return self.name != other.name or (
            self.config_hash is not None and other.config_hash is not None
            and self.config_hash != other.config_hash
        )


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
