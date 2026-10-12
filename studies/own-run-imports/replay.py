"""Run the real SWE-bench CSV exporter on malformed and valid personal-run reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = "astropy__astropy-12907"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exporter", type=Path, default=ROOT / "studies/swe-bench-verified/to_csv.py")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    cases = []
    for key in ["resolved_ids", "resolved"]:
        for name, value in [
            ("null", None),
            ("false", False),
            ("zero", 0),
            ("object", {}),
            ("string", ""),
            ("task-string", TASK),
            ("null-item", [TASK, None]),
            ("nested-list", [[TASK]]),
            ("object-ids", {TASK: True}),
        ]:
            cases.append((f"{key}-{name}", {key: value}, False))
    for name, report in [
        ("empty-primary", {"resolved_ids": [], "resolved": [TASK]}),
        ("empty-secondary", {"resolved_ids": [TASK], "resolved": []}),
        ("null-primary", {"resolved_ids": None, "resolved": [TASK]}),
        ("null-secondary", {"resolved_ids": [TASK], "resolved": None}),
    ]:
        cases.append((name, report, False))
    for name, report in [
        ("empty-modern", {"resolved_ids": []}),
        ("empty-legacy", {"resolved": []}),
        ("empty-both", {"resolved_ids": [], "resolved": []}),
        ("modern", {"resolved_ids": [TASK]}),
        ("legacy", {"resolved": [TASK]}),
        ("equal-aliases", {"resolved_ids": [TASK, TASK], "resolved": [TASK]}),
    ]:
        cases.append((name, report, True))
    (args.work / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    result = {"python": sys.version.split()[0], "cases": {}}
    data = ROOT / "studies/swe-bench-verified/data/outcomes.json"
    command = [sys.executable, str(args.exporter), "--data", str(data)]
    for name, report, valid in cases:
        path = args.work / f"{name}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        process = subprocess.run([*command, "--mine", f"my-run={path}"], text=True, capture_output=True)
        rows = list(csv.DictReader(io.StringIO(process.stdout)))
        result["cases"][name] = {
            "valid": valid,
            "exit": process.returncode,
            "rows": len(rows),
            "resolved": sum(row["score"] == "1" for row in rows),
            "csv_sha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
            "error": process.stderr.strip().splitlines()[-1].replace(str(args.work), "<work>")
            if process.stderr
            else "",
            "traceback": "Traceback" in process.stderr,
        }
        if not args.observe_only:
            if valid:
                assert process.returncode == 0 and len(rows) == 500, name
            else:
                assert process.returncode == 1 and not process.stdout and "Traceback" not in process.stderr, (
                    name
                )
    # Preserve documented complete-benchmark scoring for every retained submission,
    # including the explicitly documented incomplete-coverage and contradictory runs.
    submissions = json.loads(data.read_text())["submissions"]
    process = subprocess.run([*command, *[s["id"] for s in submissions]], capture_output=True)
    assert process.returncode == 0, process.stderr
    result["retained_submissions"] = {
        "count": len(submissions),
        "rows": len(list(csv.DictReader(io.StringIO(process.stdout.decode())))),
        "csv_sha256": hashlib.sha256(process.stdout).hexdigest(),
    }
    path = args.work / "plain.txt"
    path.write_text(TASK + "\n" + TASK + "\n")
    process = subprocess.run([*command, "--mine", f"my-run={path}"], capture_output=True)
    assert process.returncode == 0, process.stderr
    result["plain_text_sha256"] = hashlib.sha256(process.stdout).hexdigest()
    assert result["plain_text_sha256"] == result["cases"]["modern"]["csv_sha256"]
    result["totals"] = {
        "malformed_rejected_cleanly": sum(
            not row["valid"] and row["exit"] == 1 and row["rows"] == 0 and not row["traceback"]
            for row in result["cases"].values()
        ),
        "malformed_accepted": sum(not row["valid"] and row["exit"] == 0 for row in result["cases"].values()),
        "valid_accepted": sum(row["valid"] and row["exit"] == 0 for row in result["cases"].values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["totals"]))


if __name__ == "__main__":
    main()
