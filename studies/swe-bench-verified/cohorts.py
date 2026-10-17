"""Decode the retained outcome packet without treating missing observations as zero.

A resolved-only packet keeps the study's documented full-benchmark convention.
An explicit evaluated mask is evidence about which per-task outcomes are present.
The official resolved / benchmark-size score has a separate denominator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskOutcomes:
    name: str
    resolved: frozenset[str]
    evaluated: frozenset[str]
    total: int

    @property
    def complete(self) -> bool:
        return len(self.evaluated) == self.total


def decode_submission(sub: dict[str, Any], instances: list[str]) -> TaskOutcomes:
    """Validate masks/counts before assigning any task an observed score."""
    if (not isinstance(instances, list) or not instances
            or any(not isinstance(iid, str) or not iid for iid in instances)
            or len(set(instances)) != len(instances)):
        raise ValueError("instances must be a nonempty list of distinct task id strings")
    name = sub.get("id")
    if not isinstance(name, str) or not name:
        raise ValueError("submission id must be a nonempty string")
    width = len(instances)

    def mask(key: str) -> int:
        value = sub.get(key)
        if (not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]+", value)
                or len(value) > (width + 3) // 4):
            raise ValueError(f"{name}: {key} must be a hexadecimal mask of at most {width} bits")
        bits = int(value, 16)
        if bits.bit_length() > width:
            raise ValueError(f"{name}: {key} has bits outside the {width}-task benchmark")
        return bits

    def count(key: str, expected: int, *, required: bool) -> None:
        if key not in sub and not required:
            return
        value = sub.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            raise ValueError(f"{name}: {key} must match the mask's {expected} task ids")

    resolved = mask("resolved")
    evaluated = mask("evaluated") if "evaluated" in sub else (1 << width) - 1
    count("n_resolved", resolved.bit_count(), required=True)
    count("n_evaluated", evaluated.bit_count(), required=False)
    if resolved & ~evaluated:
        raise ValueError(f"{name}: resolved task ids must be included in evaluated task ids")
    return TaskOutcomes(
        name,
        frozenset(iid for i, iid in enumerate(instances) if resolved & (1 << (width - i - 1))),
        frozenset(iid for i, iid in enumerate(instances) if evaluated & (1 << (width - i - 1))),
        width,
    )
