"""Replay retained native captures against source or an installed wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

from errorbars.inputs import load_inputs
from errorbars.leaderboard import build_leaderboard

HERE = Path(__file__).resolve().parent


def run(out: Path) -> dict:
    captures = HERE / "captures"
    specs = [str(captures / name) for name in ("precise", "noisy")]
    files = sorted(captures.rglob("*.json")) + sorted(captures.rglob("*.jsonl"))
    oracle = {}
    for label in ("precise", "noisy"):
        metadata = json.loads(next((captures / label).rglob("results_*.json")).read_text())
        oracle[label] = {
            metric: metadata["results"]["metric_contract"][metric + ",none"]
            for metric in ("mean_nll", "likelihood", "perplexity")
        }
    cases = []
    for metric in ("mean_nll", "likelihood", "perplexity"):
        expected_order = sorted(
            oracle, key=lambda label: oracle[label][metric], reverse=metric == "likelihood",
        )
        try:
            data = load_inputs(specs, metric=metric).data
            board = build_leaderboard(data)
            actual_order = [entry.model for entry in board.entries]
            means = {entry.model: entry.mean for entry in board.entries}
            case = {
                "metric": metric, "status": "accepted", "expected_order": expected_order,
                "actual_order": actual_order, "order_matches": actual_order == expected_order,
                "harness_values": {label: scores[metric] for label, scores in oracle.items()},
                "errorbars_means": means,
                "means_match_harness": all(
                    math.isclose(means[label], oracle[label][metric]) for label in oracle
                ),
                "higher_is_better": getattr(board, "higher_is_better", None),
                "direction_source": getattr(board, "direction_source", None),
            }
        except ValueError as exc:
            case = {"metric": metric, "status": "refused",
                    "reason": str(exc).replace(str(HERE), "studies/metric-contract")}
        command = [sys.executable, "-m", "errorbars.cli", "leaderboard", *specs, "--metric", metric, "--json"]
        cli = subprocess.run(command, text=True, capture_output=True, check=False)
        case["cli_exit"] = cli.returncode
        case["cli_traceback"] = "Traceback" in cli.stderr
        case["cli_stdout"] = bool(cli.stdout.strip())
        if cli.returncode == 0:
            parsed = json.loads(cli.stdout)
            case["cli_order"] = [entry["model"] for entry in parsed["entries"]]
            case["cli_means"] = {entry["model"]: entry["mean"] for entry in parsed["entries"]}
        else:
            case["cli_stderr"] = cli.stderr.strip().replace(str(HERE), "studies/metric-contract")
        cases.append(case)
    result = {
        "python": platform.python_version(),
        "inputs": [{"path": str(path.relative_to(HERE)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size} for path in files],
        "cases": cases,
        "wrong_rankings": sum(case.get("order_matches") is False for case in cases),
        "mislabelled_metric_means": sum(case.get("means_match_harness") is False for case in cases),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    result = run(parser.parse_args().out)
    print(json.dumps({key: value for key, value in result.items() if key != "inputs"}, indent=2))
