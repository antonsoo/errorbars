"""Independent integer-rational and SciPy checks for the finite binomial tail."""

import json
import math
import platform
from pathlib import Path

import scipy
from scipy.stats import binomtest

from errorbars.compare import _binomial_half_two_sided

ROOT = Path(__file__).resolve().parent


def rational(total: int, k: int) -> float:
    coefficient = numerator = 1
    for i in range(1, k + 1):
        coefficient = coefficient * (total - i + 1) // i
        numerator += coefficient
    # The complete two-sided numerator is rounded only once, including subnormals.
    return min(1.0, numerator / (2 ** (total - 1)))


def main() -> None:
    cases = []
    for total in range(1, 129):
        for k in range(total // 2 + 1):
            cases.append((total, k, "integer-rational"))
    for total in (129, 255, 511, 1023, 1024, 1073, 1074, 1075, 1076, 1200, 2000, 4096):
        for k in sorted({0, 1, 11, total // 4, total // 2 - 1, total // 2}):
            cases.append((total, k, "integer-rational"))
    for total in (10_000, 10_001, 100_000, 100_001, 200_000, 1_000_000):
        for z in (0, .1, .5, 1, 2, 4, 6, 8, 12, 20, 30, 38):
            k = max(0, total // 2 - int(z * math.sqrt(total) / 2))
            cases.append((total, k, "scipy.stats.binomtest"))
    observations = []
    for total, k, oracle in cases:
        expected = (
            rational(total, k) if oracle == "integer-rational" else float(binomtest(k, total, .5).pvalue)
        )
        actual = _binomial_half_two_sided(total, k)
        close = math.isclose(actual, expected, rel_tol=2e-11, abs_tol=4 * math.ulp(0.0))
        observations.append({"discordant": total, "k": k, "oracle": oracle,
                             "actual": actual, "expected": expected, "agrees": close})
    # Record the limits of the installed SciPy oracle rather than treating its
    # underflowed zeros as proof that a positive rational probability is wrong.
    scipy_extremes = [
        {"discordant": total, "k": k, "integer_rational": rational(total, k),
         "scipy": float(binomtest(k, total, .5).pvalue),
         "actual": _binomial_half_two_sided(total, k)}
        for total, k in [(1075, 0), (1075, 11), (1076, 1)]
    ]
    result = {"python": platform.python_version(), "scipy": scipy.__version__,
              "comparisons": len(observations), "mismatches": sum(not o["agrees"] for o in observations),
              "relative_tolerance": 2e-11, "absolute_tolerance_subnormal_ulps": 4,
              "scipy_extreme_tail_observations": scipy_extremes, "observations": observations}
    (ROOT / "results/oracles.json").write_text(json.dumps(result, indent=2) + "\n")
    print({key: result[key] for key in ["comparisons", "mismatches", "scipy"]})
    assert result["mismatches"] == 0, [o for o in observations if not o["agrees"]]


if __name__ == "__main__":
    main()
