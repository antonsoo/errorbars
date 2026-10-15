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


@pytest.mark.parametrize("n01,n10", [(0, 1075), (1, 1075), (11, 1064), (99_500, 100_500)])
def test_scaled_tail_keeps_tiny_probabilities_and_large_balanced_comparisons(n01, n10):
    import math

    a = [0] * n01 + [1] * n10
    b = [1] * n01 + [0] * n10
    result = mcnemar_exact(a, b)
    if n01 + n10 <= 1076:
        expected = sum(math.comb(n01 + n10, k) for k in range(n01 + 1)) / 2 ** (n01 + n10 - 1)
    else:
        expected = binomtest(n01, n01 + n10, .5).pvalue
    assert result.p_value == pytest.approx(expected, rel=2e-11, abs=math.ulp(0.0) * 4)
    if n01 == 0:
        assert result.p_value == math.ulp(0.0)
    assert mcnemar_exact(b, a).p_value == result.p_value
