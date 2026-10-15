"""Replay the real CLI, including from a bare installed wheel, without test dependencies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

import errorbars.leaderboard

HERE = Path(__file__).resolve().parent
NS = {"s": "http://www.w3.org/2000/svg"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cases = {
        "single-continuous": ([0.25], "fewer_than_two_questions"),
        "repeated-binary": ([0., 1., 1.], "fewer_than_two_questions"),
        "single-binary": ([1.], "available"),
    }
    records = {}
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        work = Path(tmp).resolve()

        def invoke(path: Path, *, plot: bool = False) -> dict:
            command = [sys.executable, "-m", "errorbars.cli", "leaderboard", str(path), "--json"]
            if plot:
                command.extend(["--plot", str(work / "board.svg")])
            result = subprocess.run(command, cwd=work, capture_output=True, text=True, check=True)
            assert not result.stderr, result.stderr
            return json.loads(result.stdout)

        payload = invoke(HERE / "scores.csv", plot=True)
        missing = next(e for e in payload["entries"] if e["model"] == "django-only")
        assert missing["n"] == 231 and missing["n_clusters"] == 1
        assert missing["se"] is missing["ci_low"] is missing["ci_high"] is None
        assert missing["interval_status"] == "fewer_than_two_clusters"
        assert len(payload["pairwise"]) == 1 and len(payload["untested_pairs"]) == 2
        before = json.loads((HERE / "results/complete-before.json").read_text())
        full = [dict(e) for e in payload["entries"] if e["model"] != "django-only"]
        for entry in full:
            assert entry.pop("interval_status") == "available"
        assert full == before["entries"] and payload["pairwise"] == before["pairwise"]
        svg = (work / "board.svg").read_text()
        rows = ET.fromstring(svg).findall("s:g", NS)
        row = next(g for g in rows if g.find("s:title", NS).text == "django-only")
        assert not row.findall("s:line", NS)
        assert row.find("s:circle", NS).attrib["fill"] == "#ffffff"
        records["swe-bench-partial"] = {
            "input_sha256": hashlib.sha256((HERE / "scores.csv").read_bytes()).hexdigest(),
            "svg_sha256": hashlib.sha256(svg.encode()).hexdigest(),
            "complete_estimates_unchanged": True,
            "complete_pair_unchanged": True,
            "output": payload,
        }
        for name, (scores, status) in cases.items():
            path = work / f"{name}.csv"
            with path.open("w") as stream:
                writer = csv.writer(stream)
                writer.writerow(["question_id", "model", "score", "sample"])
                writer.writerows(["q1", "partial", score, i] for i, score in enumerate(scores))
                writer.writerows([["q1", "full", 0.2, 0], ["q2", "full", 0.6, 0]])
            result = invoke(path, plot=True)
            entry = next(e for e in result["entries"] if e["model"] == "partial")
            assert entry["interval_status"] == status
            assert entry["n"] == 1 and entry["n_observations"] == len(scores)
            assert entry["mean"] == sum(scores) / len(scores)
            assert len(result["untested_pairs"]) == 1 and not result["pairwise"]
            records[name] = result
        path = work / "all-descriptive.csv"
        path.write_text("question_id,model,score\nq1,a,0.2\nq1,b,0.4\n")
        result = invoke(path, plot=True)
        assert all(e["se"] is e["ci_low"] is e["ci_high"] is None for e in result["entries"])
        assert "Descriptive means only" in (work / "board.svg").read_text()
        records["all-descriptive"] = result
    output = {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "module_sha256": hashlib.sha256(Path(errorbars.leaderboard.__file__).read_bytes()).hexdigest(),
        "cases": records,
    }
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"cases": len(records), "python": output["python"], "numpy": output["numpy"]}))


if __name__ == "__main__":
    main()
