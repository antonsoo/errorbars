"""Planning feasibility checked against joint cells, not the interval formulas."""

from decimal import Decimal, localcontext
from itertools import product
from math import inf, nextafter

import pytest

from errorbars.power import (
    BinaryFeasibilityError,
    binary_effect_range,
    minimum_detectable_effect,
    questions_needed,
)


def joint_cells(p: float, rho: float, delta: float) -> list[Decimal]:
    """Evaluate the four joint probabilities at the exact float inputs."""
    with localcontext() as context:
        context.prec = 70
        p_, r_, d_ = map(Decimal.from_float, (p, rho, delta))
        q = p_ + d_
        both = p_ * q + r_ * (p_ * (1 - p_) * q * (1 - q)).sqrt()
        return [both, p_ - both, q - both, 1 - p_ - q + both]


@pytest.mark.parametrize("p,rho,delta", [(0.8, 1, 0.05), (0.9, 0.9, 0.05), (0.2, -0.5, 0.03)])
def test_impossible_pairs_do_not_get_precise_budgets(p: float, rho: float, delta: float) -> None:
    assert min(joint_cells(p, rho, delta)) < 0
    with pytest.raises(BinaryFeasibilityError):
        questions_needed(delta, baseline_accuracy=p, rho=rho)


def test_joint_probability_grid() -> None:
    checked = 0
    for p, rho, delta in product(
        [0.001, 0.01, 0.05, 0.1, 0.2, 0.4, 0.49, 0.5, 0.51, 0.8, 0.9, 0.99, 0.999],
        [-1, -0.99, -0.95, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 0.95, 0.99, 1],
        [1e-12, 0.0001, 0.001, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8],
    ):
        if p + delta >= 1:
            continue
        smallest = min(joint_cells(p, rho, delta))
        # Exact binary floats at mathematical boundaries can land a few ulps
        # outside them. Boundary behavior is tested separately below.
        if abs(smallest) < Decimal("1e-15"):
            continue
        try:
            accepted = binary_effect_range(p, rho).contains(delta)
        except BinaryFeasibilityError:
            accepted = False
        assert accepted == (smallest >= 0), (p, rho, delta, smallest)
        checked += 1
    assert checked > 1500


def test_actual_two_by_two_tables_have_feasible_forward_and_inverse_plans() -> None:
    checked = 0
    with localcontext() as context:
        context.prec = 70
        for total in [5, 10, 20, 40]:
            for both in range(total + 1):
                for only_a in range(total - both + 1):
                    for only_b in range(total - both - only_a + 1):
                        p = Decimal(both + only_a) / total
                        q = Decimal(both + only_b) / total
                        if not 0 < p < q < 1:
                            continue
                        rho = (Decimal(both) / total - p * q) / (p * (1-p) * q * (1-q)).sqrt()
                        # Inward rounding keeps table-derived rho at the boundary.
                        pf, rf, delta = float(p), nextafter(float(rho), 0), float(q - p)
                        result = questions_needed(delta, baseline_accuracy=pf, rho=rf)
                        mde = minimum_detectable_effect(result.n_questions, baseline_accuracy=pf, rho=rf)
                        assert mde <= delta * (1 + 1e-13)
                        assert min(joint_cells(pf, rf, mde)) > Decimal("-1e-14")
                        checked += 1
    assert checked == 6776


def test_negative_pairing_can_set_a_budget_independent_minimum() -> None:
    for budget in [100, 1000, 1_000_000_000]:
        mde = minimum_detectable_effect(budget, baseline_accuracy=0.2, rho=-0.5)
        assert mde == pytest.approx(0.3)
        assert min(joint_cells(0.2, -0.5, mde)) > Decimal("-1e-16")
        assert min(joint_cells(0.2, -0.5, mde - 1e-8)) < 0
    assert questions_needed(0.3, baseline_accuracy=0.2, rho=-0.5).n_questions == 42
    with pytest.raises(BinaryFeasibilityError, match="budget cannot detect"):
        minimum_detectable_effect(2, baseline_accuracy=0.2, rho=-0.5)


def test_perfect_pairing_and_nearly_perfect_pairing_are_distinct() -> None:
    with pytest.raises(BinaryFeasibilityError, match="no positive improvement"):
        minimum_detectable_effect(100, baseline_accuracy=0.8, rho=1)
    with pytest.raises(BinaryFeasibilityError):
        questions_needed(1e-16, baseline_accuracy=0.8, rho=1)
    bounds = binary_effect_range(0.5, nextafter(1, 0))
    assert 0 < bounds.maximum_delta < 1e-15
    assert bounds.contains(bounds.maximum_delta)
    assert not bounds.contains(2 * bounds.maximum_delta)
    assert not bounds.contains(inf)
    for p in [0.1, 0.2, 0.4, 0.49]:
        mde = minimum_detectable_effect(1_000_000_000, baseline_accuracy=p, rho=-1)
        assert mde == pytest.approx(1 - 2*p)
    for p in [0.5, 0.8]:
        with pytest.raises(BinaryFeasibilityError):
            binary_effect_range(p, -1)


def test_constant_target_has_no_pearson_correlation() -> None:
    bounds = binary_effect_range(0.5, 0)
    assert not bounds.maximum_inclusive
    assert not bounds.contains(0.5)
    assert bounds.contains(nextafter(0.5, 0))
    with pytest.raises(BinaryFeasibilityError):
        questions_needed(0.5, baseline_accuracy=0.5)
    # Computing p*(1-p)/p can shrink this open interval by an extra ulp.
    p = 0.2094563824951179
    delta = nextafter(1 - p, 0)
    assert p + delta < 1
    assert binary_effect_range(p, 0).maximum_delta == 1 - p
    assert questions_needed(delta, baseline_accuracy=p).n_questions >= 2


def test_joint_bernoulli_constraints_do_not_claim_to_validate_other_score_models() -> None:
    assert questions_needed(0.05, variance=0.16, rho=1).binary_feasibility is None
    repeated = questions_needed(
        0.05, baseline_accuracy=0.8, rho=1, samples_per_question=2, repeat_correlation=0.5,
    )
    assert repeated.binary_feasibility is None
    assert repeated.as_dict()["binary_feasibility"] is None
    assert minimum_detectable_effect(100, variance=0.16, rho=1) == 0
