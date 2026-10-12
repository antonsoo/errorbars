"""Independent Decimal joint-cell and integer-table oracle for both implementations.

No outcome simulation or power-calibration claim: this checks feasibility only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from collections import Counter
from decimal import Decimal as D  # noqa: N817 - conventional short name in the joint-cell equations
from decimal import localcontext
from itertools import product
from pathlib import Path

from errorbars.power import BinaryFeasibilityError, minimum_detectable_effect, questions_needed

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def cells(p: D, rho: D, delta: D) -> list[D]:
    q = p + delta
    both = p*q + rho*(p*(1-p)*q*(1-q)).sqrt()
    return [both, p-both, q-both, 1-p-q+both]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, expected, boundaries = [], [], []
    counts: Counter[str] = Counter()
    smallest_returned_cell = D(0)
    with localcontext() as context:
        context.prec = 70
        for p, rho, delta in product(
            [.001, .01, .05, .1, .2, .4, .49, .5, .51, .8, .9, .99, .999],
            [-1, -.99, -.95, -.8, -.5, -.2, 0, .2, .5, .8, .95, .99, 1],
            [1e-12, .0001, .001, .01, .02, .03, .05, .1, .2, .3, .4, .5, .6, .8],
        ):
            pd, rd, dd = map(D.from_float, (p, rho, delta))
            if not pd < pd + dd < 1:
                continue
            margin = min(cells(pd, rd, dd))
            try:
                result = questions_needed(delta, baseline_accuracy=p, rho=rho)
                output = {"n": result.n_questions}
                accepted = True
            except BinaryFeasibilityError:
                output, accepted = {"unavailable": True}, False
            except ValueError as error:
                # The tiny-effect probe can require more than 2**53 questions.
                # Retest feasibility at a low enough alpha/variance is not the
                # same input; use the public bounds only for these range cases.
                assert "representable planning range" in str(error)
                from errorbars.power import binary_effect_range
                accepted = binary_effect_range(p, rho).contains(delta)
                counts["countRangeExcludedFromParity"] += 1
                output = None
            counts["grid"] += 1
            counts["exactGridFeasible"] += margin >= 0
            if accepted != (margin >= 0):
                assert abs(margin) < D("1e-15"), (p, rho, delta, margin, accepted)
                boundaries.append(dict(p=p, rho=rho, delta=delta, minimumCell=str(margin), accepted=accepted))
            if output is not None:
                rows.append(dict(p=p, rho=rho, delta=delta))
                expected.append(output)
        for total in [5, 10, 20, 40]:
            for both in range(total + 1):
                for only_a in range(total - both + 1):
                    for only_b in range(total - both - only_a + 1):
                        p, q = D(both + only_a)/total, D(both + only_b)/total
                        if not 0 < p < q < 1:
                            continue
                        rho = (D(both)/total - p*q)/(p*(1-p)*q*(1-q)).sqrt()
                        pf, rf, delta = float(p), math.nextafter(float(rho), 0), float(q-p)
                        result = questions_needed(delta, baseline_accuracy=pf, rho=rf)
                        mde = minimum_detectable_effect(result.n_questions, baseline_accuracy=pf, rho=rf)
                        margin = min(cells(D.from_float(pf), D.from_float(rf), D.from_float(mde)))
                        smallest_returned_cell = min(smallest_returned_cell, margin)
                        assert margin > D("-1e-14") and mde <= delta*(1+1e-13)
                        counts["integerTables"] += 1
                        rows.extend([
                            dict(p=pf, rho=rf, delta=delta), dict(p=pf, rho=rf, n=result.n_questions),
                        ])
                        expected.extend([dict(n=result.n_questions), dict(mde=mde)])
    assert counts["integerTables"] == 6776
    encoded = json.dumps(rows).encode()
    native = subprocess.run([args.node, str(HERE / "check.mjs"), str(ROOT / "web/src/power.ts")],
                            input=encoded, capture_output=True, check=True)
    actual = json.loads(native.stdout)
    assert len(actual) == len(expected)
    maximum_effect_difference = 0.0
    count_rounding = []
    for row, wanted, got in zip(rows, expected, actual, strict=True):
        assert wanted.keys() == got.keys(), (row, wanted, got)
        if "mde" in wanted:
            difference = abs(wanted["mde"] - got["mde"])
            assert difference <= abs(wanted["mde"]) * 1e-14, (row, wanted, got)
            maximum_effect_difference = max(maximum_effect_difference, difference)
        elif "n" in wanted:
            if wanted["n"] != got["n"]:
                assert abs(wanted["n"] - got["n"]) <= 1, (row, wanted, got)
                count_rounding.append(dict(inputs=row, python=wanted, typescript=got))
        else:
            assert wanted == got
    report = dict(
        scope="Joint Bernoulli feasibility; does not validate normal-approximation power",
        python=platform.python_version(),
        node=subprocess.check_output([args.node, "--version"], text=True).strip(),
        decimalPrecision=70, tableTotals=[5, 10, 20, 40], counts=dict(counts),
        floatingBoundaryDifferences=boundaries,
        smallestReturnedJointCell=str(smallest_returned_cell),
        crossLanguageCases=len(rows), inputSha256=hashlib.sha256(encoded).hexdigest(),
        maximumMdeDifference=maximum_effect_difference, questionCountRounding=count_rounding,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(counts=counts, parityCases=len(rows), countRounding=len(count_rounding))))


if __name__ == "__main__":
    main()
