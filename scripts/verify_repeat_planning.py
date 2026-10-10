"""Replay repeated-answer plans and a real-score pilot through an installed CLI.

Only the standard library is needed by this verifier. No model calls or downloads.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    command = [str(args.executable)] if args.executable else [sys.executable, "-m", "errorbars.cli"]

    def run(*arguments: str) -> dict:
        process = subprocess.run(
            [*command, *arguments, "--json"], capture_output=True, text=True, check=True, timeout=60
        )
        return json.loads(process.stdout)

    counterexamples = []
    for r, n in [(0, 16), (0.8, 1259), (1, 1570)]:
        report = run(
            "power",
            "--delta",
            "0.05",
            "--baseline",
            "0.5",
            "--samples-per-question",
            "100",
            "--repeat-correlation",
            str(r),
        )
        assert report["n_questions"] == n and report["repeat_correlation"] == r
        counterexamples.append(report)
    for direction in [("--delta", "0.05"), ("--n", "500")]:
        refused = subprocess.run(
            [*command, "power", *direction, "--baseline", "0.5", "--samples-per-question", "100", "--json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert refused.returncode != 0 and refused.stdout == "" and "--repeat-correlation" in refused.stderr

    source = ROOT / "studies/repeated-planning"
    manifest = json.loads((source / "manifest.json").read_text())
    packed = (source / "outcomes.json.gz").read_bytes()
    digest = hashlib.sha256(packed).hexdigest()
    assert digest == manifest["outcomes_sha256"]
    dataset = json.loads(gzip.decompress(packed))["datasets"][0]
    groups = [[int(bit) for bit in q["correct"][:20]] for q in dataset["questions"]]
    within = statistics.mean(statistics.variance(group) for group in groups)
    between = max(0, statistics.variance(statistics.mean(group) for group in groups) - within / 20)
    variance = within + between
    r = between / variance
    with tempfile.TemporaryDirectory(prefix="errorbars-repeat-pilot-") as scratch:
        path = Path(scratch) / "pilot.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["question_id", "model", "sample", "score"])
            for q, group in zip(dataset["questions"], groups, strict=True):
                writer.writerows([q["question_id"], "Llama-3-8B-Instruct", i, v] for i, v in enumerate(group))
        summary = run("summarize", str(path))
        assert summary["n_questions"] == 127 and summary["n_observations"] == 2540
        assert math.isclose(summary["within_between"]["var_within"], within, rel_tol=1e-12)
        assert math.isclose(summary["within_between"]["var_between"], between, rel_tol=1e-12)
        plans = []
        for k in [1, 10, 100]:
            inputs = (
                "--variance",
                str(variance),
                "--repeat-correlation",
                str(r),
                "--samples-per-question",
                str(k),
            )
            plan = run("power", "--delta", "0.05", *inputs)
            z = statistics.NormalDist().inv_cdf(0.975) + statistics.NormalDist().inv_cdf(0.8)
            expected = max(2, math.ceil(z**2 * 2 * (between + within / k) / 0.05**2))
            assert plan["n_questions"] == expected
            inverse = run("power", "--n", str(expected), *inputs)
            assert inverse["mde"] <= 0.05 and inverse["repeat_correlation"] == r
            plans.append(plan)
    output = {
        "source_outcomes_sha256": digest,
        "counterexamples": counterexamples,
        "unknown_repeat_dependence": "refused in both planning directions with no JSON result",
        "pilot": {
            "source": dataset["source"],
            "draws_per_question": 20,
            "summary": summary,
            "repeat_correlation": r,
            "plans": plans,
            "scope": "Hypothetical two-model designs with this pilot variance, equal model variances "
            "and rho=0; not a power estimate for the actual 8B-versus-70B comparison.",
        },
    }
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print("Verified: dependence guards, three correlation scenarios, real pilot summaries and inverse plans.")


if __name__ == "__main__":
    main()
