"""Independent reference calculations for tests.

``cr2_mean_oracle`` evaluates the bias-reduced cluster-robust variance and its
Satterthwaite degrees of freedom from the general regression definitions (Bell
& McCaffrey 2002; Pustejovsky & Tipton 2018) with dense matrices and an
intercept-only design. It shares no code with the closed forms in
``errorbars.stats``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def _inverse_sqrt(matrix: np.ndarray) -> np.ndarray:
    values, vectors = np.linalg.eigh(matrix)
    return (vectors / np.sqrt(values)) @ vectors.T


def cr2_mean_oracle(y: Sequence[float], groups: Sequence[Any]) -> tuple[float, float]:
    """(CR2 standard error, Satterthwaite degrees of freedom) of the mean of ``y``."""
    y_arr = np.asarray(y, dtype=float)
    n = y_arr.size
    x = np.ones((n, 1))
    bread = np.linalg.inv(x.T @ x)
    annihilator = np.eye(n) - x @ bread @ x.T
    resid = annihilator @ y_arr
    meat = np.zeros((1, 1))
    columns = []
    for label in dict.fromkeys(groups):
        rows = np.array([i for i, g in enumerate(groups) if g == label])
        adjust = _inverse_sqrt(annihilator[np.ix_(rows, rows)])
        score = x[rows].T @ adjust @ resid[rows]
        meat += np.outer(score, score)
        # The variance estimate is sum_g (column_g' y)^2; its distribution under
        # independent, equal-variance scores follows from these columns' Gram matrix.
        columns.append((annihilator[:, rows] @ adjust @ x[rows] @ bread).ravel())
    variance = (bread @ meat @ bread)[0, 0]
    eigenvalues = np.linalg.eigvalsh(np.column_stack(columns).T @ np.column_stack(columns))
    dof = eigenvalues.sum() ** 2 / (eigenvalues**2).sum()
    return float(np.sqrt(variance)), float(dof)
