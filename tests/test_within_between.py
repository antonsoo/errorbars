from __future__ import annotations

import numpy as np
import pytest

from errorbars.stats import is_binary, within_between_variance


def test_within_between_variance_no_within_noise() -> None:
    # Each question's repeated samples are identical -> within variance 0,
    # all variance is between-question.
    values = [1.0, 1.0, 1.0, 5.0, 5.0, 5.0, 9.0, 9.0, 9.0]
    qids = ["q1", "q1", "q1", "q2", "q2", "q2", "q3", "q3", "q3"]
    var_w, var_b = within_between_variance(values, qids)
    assert var_w == pytest.approx(0.0, abs=1e-9)
    assert var_b > 0


def test_within_between_variance_no_between_noise() -> None:
    # Every question has the same true mean; all spread comes from repeated
    # sampling within questions.
    rng = np.random.default_rng(0)
    qids = [f"q{i}" for i in range(30) for _ in range(4)]
    values = list(rng.normal(0.5, 0.2, size=len(qids)))
    var_w, var_b = within_between_variance(values, qids)
    assert var_b == pytest.approx(0.0, abs=0.02)
    assert var_w > 0


def test_within_between_variance_recovers_known_components() -> None:
    rng = np.random.default_rng(1)
    n_q, k = 400, 5
    true_var_between = 0.3
    true_var_within = 0.1
    qids, values = [], []
    for q in range(n_q):
        item_mean = rng.normal(0, np.sqrt(true_var_between))
        for _ in range(k):
            qids.append(f"q{q}")
            values.append(item_mean + rng.normal(0, np.sqrt(true_var_within)))
    var_w, var_b = within_between_variance(values, qids)
    assert var_w == pytest.approx(true_var_within, rel=0.15)
    assert var_b == pytest.approx(true_var_between, rel=0.2)


@pytest.mark.parametrize(
    "values,expected",
    [([0, 1, 1, 0], True), ([0.0, 1.0], True), ([0.5, 1.0], False), ([], False)],
)
def test_is_binary(values: list[float], expected: bool) -> None:
    assert is_binary(values) is expected
