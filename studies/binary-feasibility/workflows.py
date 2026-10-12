"""Exercise the installed CLI; retain complete output for before/after review."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

CASES = [
    ("perfect-positive", ["--baseline", ".8", "--rho", "1", "--delta", ".05"], "error"),
    ("high-positive", ["--baseline", ".9", "--rho", ".9", "--delta", ".05"], "error"),
    ("perfect-inverse", ["--baseline", ".8", "--rho", "1", "--n", "100"], "error"),
    ("negative-small-gap", ["--baseline", ".2", "--rho", "-.5", "--delta", ".03"], "error"),
    ("negative-minimum", ["--baseline", ".2", "--rho", "-.5", "--n", "1000"], "minimum"),
    ("insufficient-budget", ["--baseline", ".9", "--rho", ".5", "--n", "100"], "error"),
    ("unavailable-sensitivity", ["--baseline", ".9", "--rho", "0", "--n", "135"], "error"),
    ("feasible-budget", ["--baseline", ".9", "--rho", ".5", "--n", "135"], "valid"),
    ("feasible-target", ["--baseline", ".9", "--rho", ".5", "--delta", ".05"], "valid"),
    ("default-plan", ["--baseline", ".5", "--rho", ".3", "--delta", ".03"], "valid"),
    ("constant-target", ["--baseline", ".5", "--delta", ".5"], "error"),
    ("continuous", ["--variance", ".16", "--rho", "1", "--n", "100"], "unchecked"),
    ("repeated", ["--baseline", ".8", "--rho", "1", "--n", "100",
                  "--samples-per-question", "2", "--repeat-correlation", ".5"], "unchecked"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", choices=["before", "after"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for name, options, expected in CASES:
        completed = subprocess.run(
            [sys.executable, "-m", "errorbars.cli", "power", *options, "--json"],
            text=True, capture_output=True, check=False,
        )
        row = dict(name=name, arguments=["power", *options, "--json"], exit=completed.returncode,
                   stdout=completed.stdout, stderr=completed.stderr)
        if args.expect == "before":
            assert completed.returncode == 0, row
        elif expected == "error":
            assert completed.returncode == 1 and not completed.stdout, row
            assert "Traceback" not in completed.stderr, row
        else:
            assert completed.returncode == 0 and not completed.stderr, row
            payload = json.loads(completed.stdout)
            assert (payload["binary_feasibility"] is None) == (expected == "unchecked"), row
            if expected == "minimum":
                assert abs(payload["mde"] - .3) < 1e-14 and payload["correlation_limited"], row
        rows.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(python=platform.python_version(), expectation=args.expect,
                                         cases=rows), indent=2) + "\n")
    print(f"Verified {len(rows)} CLI cases ({args.expect}).")


if __name__ == "__main__":
    main()
