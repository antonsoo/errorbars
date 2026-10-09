"""Replay binary, clustered and repeated-generation inputs through an installed CLI.

Uses only the standard library. Native lm-eval outcomes are paired by their
record IDs and checked against an exact binomial calculation, independently
of Errorbars' reader and test-selection implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    command = [str(args.executable)] if args.executable else [sys.executable, "-m", "errorbars.cli"]
    paths = {
        "two_questions": ROOT / "examples/leaderboard-tests/two-questions.csv",
        "repeated": ROOT / "examples/leaderboard-tests/repeated.csv",
        "clustered": ROOT / "examples/data/reading_comprehension.csv",
        "lm_eval_copa": ROOT / "tests/fixtures/lm_eval_output",
    }
    methods = {
        "two_questions": "mcnemar_exact",
        "repeated": "paired_t",
        "clustered": "clustered_t",
        "lm_eval_copa": "mcnemar_exact",
    }
    results = {}
    inputs = {}
    for name, path in paths.items():
        process = subprocess.run(
            [*command, "leaderboard", str(path), "--json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        report = json.loads(process.stdout)
        pairs = report["pairwise"]
        assert pairs and {p["test"] for p in pairs} == {methods[name]}
        for pair in pairs:
            value = (
                pair["p_value_clustered"]
                if pair["test"] == "clustered_t"
                else (pair["mcnemar"]["p_value"] if pair["test"] == "mcnemar_exact" else pair["p_value"])
            )
            assert value == pair["p_value_used"]
        # Separate recurrence checks that every selected test enters one family.
        ordered = sorted(pairs, key=lambda p: p["p_value_used"])
        running = 0.0
        for index, pair in enumerate(ordered):
            running = max(running, min(1.0, (len(pairs) - index) * pair["p_value_used"]))
            assert math.isclose(pair["p_holm"], running, abs_tol=1e-14)
        if name == "two_questions":
            assert pairs[0]["p_holm"] == 0.5
            assert report["groups"] == [["candidate", "baseline"]]
        if name == "repeated":
            assert pairs[0]["warnings"]  # Degenerate t diagnostic remains explicit.
        if name == "lm_eval_copa":
            by_model = {}
            for metadata in sorted(path.glob("*/results_*.json")):
                payload = json.loads(metadata.read_text())
                model = payload["config"]["model_args"]["pretrained"]
                samples = next(metadata.parent.glob("samples_*.jsonl"))
                records = [json.loads(line) for line in samples.read_text().splitlines()]
                by_model[model] = {row["doc_id"]: row["acc"] for row in records}
                assert len(by_model[model]) == len(records) == 20
            pair = pairs[0]
            a, b = by_model[pair["model_a"]], by_model[pair["model_b"]]
            assert a.keys() == b.keys()
            n01 = sum(a[q] == 0 and b[q] == 1 for q in a)
            n10 = sum(a[q] == 1 and b[q] == 0 for q in a)
            n = n01 + n10
            exact = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(n01, n10) + 1)) / 2**n)
            assert pair["mcnemar"] == {"n01": n01, "n10": n10, "p_value": exact}
            assert pair["p_holm"] == exact
        results[name] = report
        sources = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        inputs.update({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"inputs_sha256": inputs, "results": results}, indent=2, allow_nan=False) + "\n"
    )
    print(f"Verified {len(results)} CLI workflows, including native lm-eval pairing and exact tails")


if __name__ == "__main__":
    main()
