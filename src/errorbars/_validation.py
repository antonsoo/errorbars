"""Array contracts shared by statistical entry points."""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


def score_vector(values: ArrayLike, name: str = "values") -> NDArray[np.float64]:
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a one-dimensional finite numeric vector") from exc
    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} must contain only finite scores")
    # Leave ample room for squared residuals and their sums in float64.
    if np.any(np.abs(arr) > 1e150):
        raise ValueError(f"{name} scores are too large to analyze")
    return arr


def group_vector(values: ArrayLike, n: int, name: str = "clusters") -> NDArray[Any]:
    arr = np.asarray(values, dtype=object)
    if arr.ndim != 1 or len(arr) != n:
        raise ValueError(f"{name} must be one-dimensional with one identifier per score")
    for value in arr:
        if isinstance(value, str):
            valid = bool(value.strip())
        else:
            valid = isinstance(value, Integral) or (isinstance(value, Real) and math.isfinite(value))
        if not valid:
            raise ValueError(f"{name} must contain nonempty, finite scalar identifiers")
    return arr


def sample_sd(values: NDArray[np.float64]) -> float:
    """Scale before squaring; a score's unit must not change statistical evidence."""
    scale = float(np.max(np.abs(values)))
    return float(np.std(values / scale, ddof=1)) * scale if scale else 0.0
