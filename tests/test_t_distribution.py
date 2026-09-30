"""The Student-t helpers used for paired and clustered inference, against scipy."""

from __future__ import annotations

import itertools

import pytest
from scipy import special
from scipy import stats as sp_stats

from errorbars.stats import regularized_incomplete_beta, t_for_confidence, t_two_sided_p

DOFS_AND_STATS = list(itertools.product([1, 2, 5, 11, 39, 199, 1e6], [0.0, 0.7, 1.96, 3.1, 8.0]))
DOFS_AND_LEVELS = list(itertools.product([1, 3, 11, 39, 199], [0.8, 0.95, 0.99]))


@pytest.mark.parametrize(("dof", "t"), DOFS_AND_STATS)
def test_two_sided_p_matches_scipy(dof: float, t: float) -> None:
    assert t_two_sided_p(t, dof) == pytest.approx(2 * sp_stats.t.sf(t, dof), rel=1e-8, abs=1e-15)
    assert t_two_sided_p(-t, dof) == t_two_sided_p(t, dof)


@pytest.mark.parametrize(("dof", "confidence"), DOFS_AND_LEVELS)
def test_critical_value_matches_scipy(dof: float, confidence: float) -> None:
    expected = sp_stats.t.ppf(0.5 + confidence / 2, dof)
    assert t_for_confidence(confidence, dof) == pytest.approx(expected, rel=1e-8)


def test_incomplete_beta_matches_scipy() -> None:
    for a, b, x in itertools.product([0.5, 2, 30], [0.5, 1, 7], [0.01, 0.4, 0.95]):
        assert regularized_incomplete_beta(a, b, x) == pytest.approx(special.betainc(a, b, x), abs=1e-13)


def test_small_samples_are_less_significant_than_the_normal_approximation() -> None:
    # The normal approximation is anti-conservative: at 8 degrees of freedom a
    # statistic of 2.2 gives p = 0.028 under the normal but 0.059 under t.
    assert t_two_sided_p(2.2, 8) > 0.05 > 2 * sp_stats.norm.sf(2.2)
