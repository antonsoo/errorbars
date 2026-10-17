"""Run the source converter and actual installed CLI on retained native outcomes.

The converter is a checkout study tool, not a file shipped in the Python wheel.
The CLI may come from a bare wheel, source distribution, or Git installation.
No development dependencies are required for this replay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import errorbars.cli

HERE = Path(__file__).resolve().parent
PARTIAL = "20260901_mini-v2.4.2_gemini-3-5-flash"
PEER = "20251205_sonar-foundation-agent_claude-opus-4-5"
CONVERTER = HERE.parent / "swe-bench-verified/to_csv.py"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    native = json.loads((HERE / "native/partial-details.json").read_text())
    oracle = json.loads((HERE / "results/oracle.json").read_text())
    run = subprocess.run(
        [sys.executable, str(CONVERTER), PARTIAL, PEER], capture_output=True, text=True, check=True,
    )
    assert "59 unobserved tasks omitted" in run.stderr
    rows = list(csv.DictReader(io.StringIO(run.stdout)))
    partial = {r["question_id"]: bool(int(r["score"])) for r in rows if r["model"] == PARTIAL}
    assert partial == {iid: record["resolved"] for iid, record in native.items()}
    assert len(rows) == 941 and len(partial) == 441
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "pair.csv"
        source.write_text(run.stdout)
        command = [sys.executable, "-m", "errorbars.cli", "compare", str(source),
                   "--model-a", PARTIAL, "--model-b", PEER, "--json"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        assert not result.stderr, result.stderr
        comparison = json.loads(result.stdout)
        for key in ("n", "n_clusters", "mean_a", "mean_b", "mean_diff", "se_clustered", "dof_clustered",
                    "ci_low_clustered", "ci_high_clustered", "p_value_clustered"):
            assert math.isclose(comparison[key], oracle[key], rel_tol=1e-10, abs_tol=1e-12), key
        for key in ("n01", "n10", "p_value"):
            assert math.isclose(comparison["mcnemar"][key], oracle["mcnemar"][key],
                                rel_tol=1e-10, abs_tol=1e-12), key
        summary_run = subprocess.run(
            [sys.executable, "-m", "errorbars.cli", "summarize", str(source),
             "--model", PARTIAL, "--json"], capture_output=True, text=True, check=True,
        )
        summary = json.loads(summary_run.stdout)
        assert summary["n"] == summary["n_observations"] == 441
        assert summary["mean"] == 359 / 441 and summary["method"] == "clustered_cr2"
    output = {
        "python": sys.version.split()[0], "numpy": np.__version__,
        "installed_cli_sha256": hashlib.sha256(Path(errorbars.cli.__file__).read_bytes()).hexdigest(),
        "converter_sha256": hashlib.sha256(CONVERTER.read_bytes()).hexdigest(),
        "native_sha256": oracle["native_sha256"],
        "csv_sha256": hashlib.sha256(run.stdout.encode()).hexdigest(),
        "csv_observations": len(rows), "converter_stderr": run.stderr,
        "comparison": comparison, "summary": summary,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"exported_observations": len(rows), "shared_tasks": comparison["n"],
                      "mean_diff": comparison["mean_diff"], "exact_p": comparison["mcnemar"]["p_value"]}))


if __name__ == "__main__":
    main()
