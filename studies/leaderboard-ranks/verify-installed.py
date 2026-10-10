"""Replay rank evidence through a separately installed CLI; standard library only."""

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
    parser.add_argument(
        "--scenario", action="append", choices=["gaps", "task-independent", "repository-clustered"]
    )
    args = parser.parse_args()
    outputs = {}
    for name in args.scenario or ("gaps", "task-independent", "repository-clustered"):
        path = ROOT / "examples/leaderboard-ranks/gaps.csv" if name == "gaps" else args.artifacts / "swe.csv"
        extra = ["--cluster-col", "none"] if name == "task-independent" else []
        command = [str(args.executable), "leaderboard", str(path), *extra]
        svg = args.artifacts / f"{name}-installed.svg"
        process = subprocess.run(
            [*command, "--json", "--plot", str(svg)],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        data = json.loads(process.stdout)
        if name == "gaps":
            assert data["rank_comparisons"]["leader"] == {
                "non_significant": [2, 5],
                "significant": [4],
                "untested": [3],
            }
            assert data["rank_comparisons"]["unmatched"]["untested"] == [1, 2, 4, 5]
            assert len(data["untested_pairs"]) == 4
            assert len(data["warnings"]) == 2
            text = subprocess.check_output(command, text=True)
            # A bare wheel has no rich. Verify its actual plain-text row, not a mock table.
            leader = next(line for line in text.splitlines() if re.match(r"\s*1\s+leader\s", line))
            assert re.search(r"2, 5\s+3$", leader)
            (args.artifacts / "gaps-installed.txt").write_text(text)
            (args.artifacts / "gaps-installed.json").write_text(process.stdout)
        else:
            expected = json.loads((args.artifacts / f"{name}.json").read_text())
            for key in ("rank_comparisons", "untested_pairs", "warnings", "groups", "alpha"):
                assert data[key] == expected[key], (name, key)
            for actual, reference in zip(data["pairwise"], expected["pairwise"], strict=True):
                for key in ("model_a", "model_b", "test", "n_shared"):
                    assert actual[key] == reference[key]
                for key in ("p_holm", "p_value_used", "mean_diff"):
                    assert math.isclose(actual[key], reference[key], rel_tol=1e-10, abs_tol=1e-12)
            for actual, reference in zip(data["entries"], expected["entries"], strict=True):
                assert actual["model"] == reference["model"]
                for key in ("mean", "se", "ci_low", "ci_high"):
                    assert math.isclose(actual[key], reference[key], rel_tol=1e-10, abs_tol=1e-12)
        # The entire plot, including wrapped labels and conclusions, must reproduce exactly.
        reference_svg = args.artifacts / ("gaps.svg" if name == "gaps" else f"{name}-after.svg")
        assert svg.read_bytes() == reference_svg.read_bytes()
        outputs[name] = {
            "models": len(data["entries"]),
            "tested_pairs": len(data["pairwise"]),
            "untested_pairs": len(data["untested_pairs"]),
            "svg_sha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
        }
        (args.artifacts / f"{name}-installed-result.json").write_text(
            json.dumps(outputs[name], indent=2) + "\n"
        )
        print(name, outputs[name], flush=True)
    (args.artifacts / "installed.json").write_text(json.dumps(outputs, indent=2) + "\n")


if __name__ == "__main__":
    main()
