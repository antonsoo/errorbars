"""Capture the real CLI on the labelled synthetic partial-cohort fixture.

Run with the Python environment whose installed/source package is being checked:
    python studies/leaderboard-overlap/reproduce.py --out /tmp/overlap.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import errorbars.leaderboard

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    fixture = HERE / "partial-cohorts.csv"
    relative = fixture.relative_to(HERE.parent.parent)
    command = ["leaderboard", str(relative), "--json"]
    result = subprocess.run(
        [sys.executable, "-m", "errorbars.cli", *command],
        cwd=HERE.parent.parent, text=True, capture_output=True, check=False,
    )
    module = Path(errorbars.leaderboard.__file__)
    record = {
        "command": ["errorbars", *command],
        "input_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "leaderboard_module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "exit_code": result.returncode,
        "stdout": json.loads(result.stdout) if result.returncode == 0 else result.stdout,
        "stderr": result.stderr,
    }
    args.out.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"exit_code": result.returncode, "artifact": str(args.out)}))


if __name__ == "__main__":
    main()
