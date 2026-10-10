"""Audit single binary comparison choices against SciPy on retained public outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

from scipy.stats import binomtest

from errorbars.compare import paired_compare, select_inference

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    path = ROOT / "studies/swe-bench-verified/data/outcomes.json"
    data = json.loads(path.read_text())
    n = len(data["instances"])
    rows = [
        r
        for r in data["submissions"]
        if r.get("reported") is None or abs(r["reported"] - 100 * r["n_resolved"] / n) <= 0.5
    ]
    outcomes = {row["id"]: int(row["resolved"], 16) for row in rows}
    vectors = {name: [int(bit) for bit in f"{bits:0{n}b}"] for name, bits in outcomes.items()}
    changed = []
    largest_error = 0.0
    for a, b in combinations(outcomes, 2):
        # Independent oracle uses integer outcome masks, not Errorbars' reader or contingency table.
        only_a = (outcomes[a] & ~outcomes[b]).bit_count()
        only_b = (outcomes[b] & ~outcomes[a]).bit_count()
        discordant = only_a + only_b
        oracle = float(binomtest(only_a, discordant, 0.5).pvalue) if discordant else 1.0
        comp = paired_compare(vectors[a], vectors[b])
        selected = select_inference(comp, single_observation_per_question=True)
        assert selected.test == "mcnemar_exact"
        error = abs(selected.p_value - oracle)
        largest_error = max(largest_error, error)
        assert math.isclose(selected.p_value, oracle, rel_tol=1e-11, abs_tol=1e-14)
        if (comp.p_value < 0.05) != (oracle < 0.05):
            changed.append(
                {
                    "model_a": a,
                    "model_b": b,
                    "only_a": only_a,
                    "only_b": only_b,
                    "paired_t_p": comp.p_value,
                    "exact_p": oracle,
                }
            )
    result = {
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "models": len(rows),
        "questions": n,
        "pairs": math.comb(len(rows), 2),
        "maximum_absolute_error_against_scipy": largest_error,
        "task_decisions_changed_at_0_05": len(changed),
        "changed_pairs": changed,
        "scope": "Single task-independent comparisons, unadjusted for browsing multiple pairs. "
        "Repository-clustered inference is a separate model and is unchanged.",
    }
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print({key: value for key, value in result.items() if key != "changed_pairs"})


if __name__ == "__main__":
    main()
