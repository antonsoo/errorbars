from __future__ import annotations

import pytest
from scipy.stats import binomtest

from errorbars.compare import mcnemar_exact


@pytest.mark.parametrize("n01,n10", [(0, 0), (1, 0), (50, 50), (50, 51), (0, 1024), (11, 3000),
                                       (6010, 5990), (49900, 50100)])
def test_exact_mcnemar_remains_a_two_sided_binomial_tail_at_scale(n01, n10):
    a = [0] * n01 + [1] * n10
    b = [1] * n01 + [0] * n10
    if not a:
        a, b = [1, 0], [1, 0]
    result = mcnemar_exact(a, b)
    expected = binomtest(n01, n01 + n10, 0.5).pvalue if n01 + n10 else 1
    assert result.n01 == n01 and result.n10 == n10
    assert result.p_value == pytest.approx(expected, rel=2e-11, abs=0)
