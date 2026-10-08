#!/usr/bin/env python3
"""Export paired-comparison test vectors from the Python implementation.

The SWE-bench Verified page re-implements the paired comparison in TypeScript
(`web/src/paired.ts`, `web/src/tdist.ts`) so it can run in the browser. Its
vitest suite checks every statistic against these vectors, computed here on
real pairs of submissions, so the two implementations cannot drift apart. Run
this after changing `errorbars.compare`, `errorbars.stats`, or the study data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from errorbars.compare import paired_compare
from errorbars.stats import t_for_confidence, t_two_sided_p

ROOT = Path(__file__).parent.parent
DATA = ROOT / "studies" / "swe-bench-verified" / "data" / "outcomes.json"
OUT_PATH = ROOT / "web" / "paired-vectors.json"

# Ranks (0 = highest score, ties by id) chosen to cover ties, small and large gaps,
# a system that resolves almost nothing, and identical outcome vectors.
PAIRS = [(0, 1), (0, 3), (0, 9), (0, 24), (2, 7), (5, 60), (10, 11), (40, 120), (0, 172), (171, 172), (6, 6)]
T_CASES = [(0.0, 3.0), (0.5, 3.331), (1.96, 499.0), (2.5, 11.0), (3.011, 3.331), (12.0, 2.0), (40.0, 499.0)]
CRITICAL_CASES = [(0.95, 499.0), (0.95, 3.3313), (0.95, 11.0), (0.9, 39.0), (0.99, 2.0)]


def build() -> dict[str, Any]:
    data = json.loads(DATA.read_text())
    instances = data["instances"]
    subs = sorted(
        (
            s
            for s in data["submissions"]
            if s["reported"] is None or abs(s["reported"] - 100 * s["n_resolved"] / len(instances)) <= 0.5
        ),
        key=lambda s: (-s["n_resolved"], s["id"]),
    )
    repo = [iid.rsplit("-", 1)[0] for iid in instances]

    def bits(sub: dict[str, Any]) -> list[float]:
        return [float(b) for b in f"{int(sub['resolved'], 16):0{len(instances)}b}"]

    pairs = []
    for i, j in PAIRS:
        comp = paired_compare(bits(subs[i]), bits(subs[j]), clusters=repo)
        assert comp.mcnemar is not None
        pairs.append(
            {
                "a": subs[i]["id"],
                "b": subs[j]["id"],
                "meanA": comp.mean_a,
                "meanB": comp.mean_b,
                "diff": comp.mean_diff,
                "se": comp.se_paired,
                "ciLow": comp.ci_low,
                "ciHigh": comp.ci_high,
                "p": comp.p_value,
                "correlation": comp.correlation,
                "onlyA": comp.mcnemar.n10,
                "onlyB": comp.mcnemar.n01,
                "mcnemarP": comp.mcnemar.p_value,
                "clusters": comp.n_clusters,
                "dofClustered": comp.dof_clustered,
                "seClustered": comp.se_clustered,
                "ciLowClustered": comp.ci_low_clustered,
                "ciHighClustered": comp.ci_high_clustered,
                "pClustered": comp.p_value_clustered,
            }
        )
    return {
        "pairs": pairs,
        "tTwoSidedP": [{"t": t, "dof": dof, "p": t_two_sided_p(t, dof)} for t, dof in T_CASES],
        "tCritical": [
            {"confidence": c, "dof": dof, "value": t_for_confidence(c, dof)} for c, dof in CRITICAL_CASES
        ],
    }


def main() -> None:
    OUT_PATH.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
