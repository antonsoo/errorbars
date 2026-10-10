"""Verify installed CLI/HTML primary tests from native logs and boundary cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    cases = [
        ("two-wins", "examples/leaderboard-tests/two-questions.csv", [], "mcnemar_exact"),
        ("repeated", "examples/leaderboard-tests/repeated.csv", [], "paired_t"),
        ("copa", "tests/fixtures/lm_eval_output", [], "mcnemar_exact"),
        (
            "clustered",
            "examples/data/reading_comprehension.csv",
            ["--model-a", "tuned-70b", "--model-b", "baseline-70b"],
            "clustered_t",
        ),
    ]
    output = {}
    for name, relative, extra, expected in cases:
        path = ROOT / relative
        html = args.artifacts / f"{name}.html"
        command = [str(args.executable), "compare", str(path), *extra]
        process = subprocess.run(
            [*command, "--json", "--html", str(html)],
            text=True,
            capture_output=True,
            check=True,
        )
        result = json.loads(process.stdout)
        document = html.read_text()
        embedded = json.loads(
            re.search(r'<script type="application/json" id="report-data">(.*?)</script>', document).group(1)
        )
        assert result["inference"] == embedded["inference"]
        assert result["inference"]["test"] == expected
        primary = result["inference"]
        if name == "two-wins":
            assert primary["p_value"] == 0.5 and primary["ci_low"] is primary["ci_high"] is None
            assert result["p_value"] == 0
        elif name == "repeated":
            assert not primary["mcnemar_applicable"]
        elif name == "clustered":
            assert primary["p_value"] == result["p_value_clustered"]
            assert primary["ci_low"] == result["ci_low_clustered"]
        else:
            # Recompute directly from lm-eval records, independently of Errorbars' adapter.
            models = {}
            for metadata in sorted(path.glob("*/results_*.json")):
                source = json.loads(metadata.read_text())
                model = source["config"]["model_args"]["pretrained"]
                samples = next(metadata.parent.glob("samples_*.jsonl"))
                records = [json.loads(line) for line in samples.read_text().splitlines()]
                models[model] = {row["doc_id"]: row["acc"] for row in records}
            a, b = models[result["model_a"]], models[result["model_b"]]
            assert a.keys() == b.keys()
            only_a = sum(a[q] == 1 and b[q] == 0 for q in a)
            only_b = sum(a[q] == 0 and b[q] == 1 for q in a)
            discordant = only_a + only_b
            exact = min(
                1.0, 2 * sum(math.comb(discordant, k) for k in range(min(only_a, only_b) + 1)) / 2**discordant
            )
            assert primary["p_value"] == exact == 0.2890625
        table = subprocess.check_output(command, text=True)
        assert "selected test" in table and "selected p-value" in table
        (args.artifacts / f"{name}.txt").write_text(table)
        sources = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        output[name] = {
            "inference": primary,
            "legacy_paired_t_p": result["p_value"],
            "headline": re.search(r'<p id="inference-description">(.*?)</p>', document).group(1),
            "input_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
            },
            "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
        }
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(f"Verified {len(output)} installed CLI/HTML workflows")


if __name__ == "__main__":
    main()
