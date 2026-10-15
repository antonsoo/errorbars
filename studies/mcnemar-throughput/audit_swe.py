"""Check the public leaderboard API on retained real SWE-bench outcomes.

This reuses the earlier study's exclusions and its task-independent diagnostic;
it does not assert independence of SWE-bench tasks or fetch a current leaderboard.
"""

import hashlib
import json
import math
from itertools import combinations
from pathlib import Path

from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard, holm_correction

ROOT = Path(__file__).resolve().parents[2]


def exact_tail(n01: int, n10: int) -> float:
    total, k = n01 + n10, min(n01, n10)
    if not total:
        return 1.0
    return min(1.0, sum(math.comb(total, i) for i in range(k + 1)) / 2 ** (total - 1))


def main() -> None:
    source = ROOT / "studies/swe-bench-verified/data/outcomes.json"
    raw = json.loads(source.read_text())
    questions = raw["instances"]
    submissions, excluded = [], []
    for row in raw["submissions"]:
        score = 100 * row["n_resolved"] / len(questions)
        if row.get("reported") is not None and abs(float(row["reported"]) - score) > .5:
            excluded.append(row["id"])
        else:
            submissions.append(row)
    qids, names, scores = [], [], []
    bits = {}
    for row in submissions:
        bits[row["id"]] = int(row["resolved"], 16)
        qids.extend(questions)
        names.extend([row["id"]] * len(questions))
        scores.extend(float(value) for value in f"{bits[row['id']]:0{len(questions)}b}")
    board = build_leaderboard(EvalData(qids, names, scores))
    expected = {}
    for a, b in combinations(bits, 2):
        n10 = (bits[a] & ~bits[b]).bit_count()
        n01 = (bits[b] & ~bits[a]).bit_count()
        expected[frozenset((a, b))] = exact_tail(n01, n10)
    exact_raw = [expected[frozenset((pair.model_a, pair.model_b))] for pair in board.pairwise]
    corrected = holm_correction(exact_raw)
    differences = []
    for pair, raw_p, adjusted in zip(board.pairwise, exact_raw, corrected, strict=True):
        assert pair.test == "mcnemar_exact"
        assert math.isclose(pair.p_value_used, raw_p, rel_tol=2e-11, abs_tol=0)
        assert math.isclose(pair.p_holm, adjusted, rel_tol=2e-11, abs_tol=0)
        if (pair.p_holm < board.alpha) != (adjusted < board.alpha):
            differences.append([pair.model_a, pair.model_b])
    output = {
        "data_scope": "retained SWE-bench study snapshot; task-independent diagnostic",
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "models": len(board.entries), "questions": len(questions), "pairs": len(board.pairwise),
        "excluded": excluded, "oracle": "integer combinations; complete two-sided numerator",
        "raw_and_holm_p_values_agree": True, "changed_significance_decisions": differences,
        "significant_pairs": sum(pair.p_holm < board.alpha for pair in board.pairwise),
        "max_absolute_raw_p_difference": max(
            abs(pair.p_value_used - expected_p)
            for pair, expected_p in zip(board.pairwise, exact_raw, strict=True)
        ),
    }
    assert not differences
    (ROOT / "studies/mcnemar-throughput/results/swe-audit.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
