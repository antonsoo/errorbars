"""Verify grading evidence through installed CLI imports and canonical roundtrips."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from errorbars.io import load_csv
from errorbars.review import review_comparison

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
        work = Path(temporary).resolve()

        def invoke(label: str, arguments: list[str], success: bool = True):
            result = subprocess.run([sys.executable, "-m", "errorbars.cli", *arguments],
                                    cwd=work, capture_output=True, text=True, check=False)
            assert result.returncode == (0 if success else 1), (label, result.stderr)
            assert "Traceback" not in result.stderr
            if not success:
                assert not result.stdout
                assert "conflicting scoring rules" in result.stderr
            checks.append({"case": label, "exit": result.returncode, "no_traceback": True})
            return result

        for other in ("folded", "strict-repeat", "improved-strict", "prompt-variant"):
            specs = [f"A={HERE / 'captures/strict'}", f"B={HERE / 'captures' / other}"]
            canonical = work / f"{other}.csv"
            invoke(other + " import", ["import", "lm-eval", *specs, "-o", str(canonical)])
            data = load_csv(canonical)
            assert len(data) == 48 and all(rule.config_hash for rule in data.scoring)
            review = review_comparison(data, "A", "B")
            conflict = other == "folded"
            expected_p = 0.0078125 if other == "improved-strict" else 1.
            assert review.cohort["n_identity_matching"] == 24
            assert review.cohort["n_scoring_conflicting"] == (24 if conflict else 0)
            if conflict:
                assert review.comparison is review.inference is None
            else:
                assert review.cohort["n_scoring_matching"] == 24
                assert review.inference.p_value == expected_p
            for kind, paths in (("native", specs), ("canonical", [str(canonical)])):
                report = work / f"{other}-{kind}.html"
                result = invoke(other + " " + kind + " compare", [
                    "compare", *paths, "--json", "--html", str(report),
                ], success=not conflict)
                assert report.is_file()
                if not conflict:
                    assert json.loads(result.stdout)["inference"]["p_value"] == expected_p
                else:
                    assert "Inference unavailable" in report.read_text()
                plot = work / "preserve.svg"
                plot.write_text("previous plot must survive refusal\n")
                invoke(other + " " + kind + " leaderboard", [
                    "leaderboard", *paths, "--json", "--plot", str(plot),
                ], success=not conflict)
                if conflict:
                    assert plot.read_text() == "previous plot must survive refusal\n"
                if args.artifacts:
                    args.artifacts.mkdir(parents=True, exist_ok=True)
                    (args.artifacts / report.name).write_bytes(report.read_bytes())
            if args.artifacts:
                (args.artifacts / canonical.name).write_bytes(canonical.read_bytes())
        result = {"python": platform.python_version(), "numpy": np.__version__,
                  "cli_workflows": len(checks), "checks": checks,
                  "native_and_canonical_contracts_match": True}
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"cli_workflows": len(checks), "python": result["python"], "numpy": result["numpy"]}))


if __name__ == "__main__":
    main()
