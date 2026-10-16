"""Replay identical-score comparisons through the active installed CLI."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

import errorbars

HERE = Path(__file__).resolve().parent


def replay(work: Path, native: bool) -> dict[str, object]:
    if work.exists() and any(work.iterdir()):
        raise ValueError("replay directory must be empty")
    work.mkdir(parents=True, exist_ok=True)
    results = {}
    for scenario, base in (("constant", [0.1]), ("same_distribution", [0.1, 0.2, 0.3])):
        source = work / f"{scenario}.csv"
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["question_id", "model", "score", "sample"])
            for model, repeat in (("once", 1), ("triple", 3), ("ten", 10)):
                for question in range(20):
                    for sample, score in enumerate(base * repeat):
                        writer.writerow([f"q{question:02}", model, repr(score), sample])
        specs = [source.name]
        results[scenario] = run_cli(specs, scenario, work)
        results[scenario]["input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    if native:
        shutil.copytree(HERE / "fixtures", work / "fixtures")
        results["inspect"] = run_cli(
            [
                "once=fixtures/epochs-1.eval",
                "triple=fixtures/epochs-3.eval",
            ],
            "inspect",
            work,
        )
    package = Path(errorbars.__file__).resolve().parent
    return {
        "version": importlib.metadata.version("errorbars"),
        "python": sys.version.split()[0],
        "native_inspect": native,
        "package_location_kind": "site-packages" if "site-packages" in package.parts else "source",
        "io_sha256": hashlib.sha256((package / "io.py").read_bytes()).hexdigest(),
        "scenarios": results,
    }


def run_cli(specs: list[str], scenario: str, work: Path) -> dict[str, object]:
    exports = {}
    for command in ("leaderboard", "compare"):
        args = [sys.executable, "-m", "errorbars.cli", command, *specs, "--json"]
        if command == "compare":
            args += ["--model-a", "once", "--model-b", "triple", "--html", f"{scenario}.html"]
        process = subprocess.run(args, cwd=work, text=True, capture_output=True, check=True)
        (work / f"{scenario}-{command}.json").write_text(process.stdout, encoding="utf-8")
        payload = json.loads(process.stdout)
        if command == "leaderboard":
            exports[command] = {"groups": payload["groups"], "pairwise": payload["pairwise"]}
        else:
            # Full JSON is written above; the concise receipt retains the actual
            # selected result and question-level differences without machine paths.
            exports[command] = {
                key: payload[key]
                for key in (
                    "mean_diff",
                    "p_value",
                    "n",
                    "n_observations_a",
                    "n_observations_b",
                    "question_identity",
                    "scoring_rules",
                    "inference",
                    "warnings",
                )
                if key in payload
            }
        exports[f"{command}_stderr"] = process.stderr.replace(str(work), "<work>")
    return exports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    result = replay(args.work.resolve(), args.native)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({name: item["leaderboard"]["groups"] for name, item in result["scenarios"].items()}))
