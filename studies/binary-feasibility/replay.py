"""Replay actual downloaded plans with the installed CLI of this interpreter."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import shlex
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plans", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = json.loads((args.plans / "browser.json").read_text())
    rows = []
    for record in capture["records"]:
        for state in record["states"]:
            if "download" not in state:
                assert state["disabled"] and not state["resultVisible"]
                continue
            raw = (args.plans / state["download"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == state["downloadSha256"]
            plan = json.loads(raw)
            assert plan["schemaVersion"] == 2
            command = shlex.split(plan["cliCommand"])
            assert command[:2] == ["errorbars", "power"]
            completed = subprocess.run([sys.executable, "-m", "errorbars.cli", *command[1:]],
                                       capture_output=True, text=True, check=True)
            assert not completed.stderr
            result = json.loads(completed.stdout)
            assert result["n_questions"] == plan["result"]["nQuestions"]
            assert math.isclose(result["mde"], plan["result"]["minimumDetectableEffect"], rel_tol=1e-14)
            assert result["correlation_limited"] == plan["result"]["correlationLimited"]
            for python_key, browser_key in [
                ("minimum_delta", "minimumDelta"), ("maximum_delta", "maximumDelta"),
                ("minimum_inclusive", "minimumInclusive"), ("maximum_inclusive", "maximumInclusive"),
                ("model", "model"),
            ]:
                assert (
                    result["binary_feasibility"][python_key]
                    == plan["result"]["binaryFeasibility"][browser_key]
                )
            rows.append(dict(download=state["download"], command=plan["cliCommand"],
                             sha256=state["downloadSha256"], result=result))
    args.output.write_text(json.dumps(dict(python=platform.python_version(), replays=rows), indent=2) + "\n")
    print(f"Reproduced {len(rows)} browser downloads with the installed CLI.")


if __name__ == "__main__":
    main()
