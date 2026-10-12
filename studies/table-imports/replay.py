"""Exercise table imports through the library and CLI; constructed data, no model calls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import subprocess
import sys
import warnings
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from errorbars.io import ColumnMap, load_csv, load_dataframe
from errorbars.review import review_comparison


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def records_digest(data):
    records = asdict(data)
    for source in records.get("sources") or []:
        if source is not None:
            source["path"] = Path(source["path"]).name
    return digest(records)


def capture(call):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            value = call()
            result = {"accepted": True, "value": value}
        except Exception as exc:
            result = {"accepted": False, "type": type(exc).__name__, "error": str(exc)}
    result["warnings"] = [str(w.message) for w in caught]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    result = {
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "dataframes": {},
        "csv": {},
        "cli": {},
    }
    rows = [
        {
            "question_id": f"q{i:02d}" + (' "quoted"\ncontinued' if i == 0 else ""),
            "model": model,
            "score": int(i % 5 < threshold),
        }
        for i in range(40)
        for model, threshold in [("A", 3), ("B", 2)]
    ]
    frame = pd.DataFrame(rows)
    for label in ["score", "question_id", "model", "cluster_id", "sample", "question_hash", "scorer", "note"]:
        ambiguous = frame.copy()
        if label not in ambiguous:
            ambiguous[label] = "first"
        second = (1 - ambiguous.score) if label == "score" else ambiguous[label]
        ambiguous.insert(len(ambiguous.columns), label, second, allow_duplicates=True)
        original = ambiguous.copy(deep=True)
        entry = capture(
            lambda ambiguous=ambiguous: (
                review_comparison(load_dataframe(ambiguous), "A", "B").comparison.mean_diff
            )
        )
        pd.testing.assert_frame_equal(ambiguous, original)
        result["dataframes"][label] = entry
    unambiguous = load_dataframe(frame)
    result["unique_dataframe_difference"] = review_comparison(unambiguous, "A", "B").comparison.mean_diff
    for name, valid, columns in [
        ("unique", frame, None),
        ("duplicate_index", frame.set_axis([0] * len(frame)), None),
        (
            "custom",
            frame.rename(columns={"question_id": "qid", "model": "mdl", "score": "acc"}),
            ColumnMap(question_id="qid", model="mdl", score="acc"),
        ),
    ]:
        data = load_dataframe(valid, columns)
        assert (data.question_id, data.model, data.score) == (
            unambiguous.question_id,
            unambiguous.model,
            unambiguous.score,
        )
        result.setdefault("valid_dataframes", {})[name] = digest([data.question_id, data.model, data.score])

    for number, (delimiter, quoting, newline, bom, eof) in enumerate(
        itertools.product(
            [",", ";", "\t"], [csv.QUOTE_MINIMAL, csv.QUOTE_ALL], ["\n", "\r\n"], [False, True], [False, True]
        )
    ):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=delimiter, quoting=quoting, lineterminator=newline)
        writer.writerow(["question_id", "model", "score", "note"])
        for row in rows:
            score = str(row["score"]) + (",0" if delimiter != "," else ".0")
            writer.writerow([row["question_id"], row["model"], score, 'note,;\t"quoted"'])
        text = stream.getvalue()
        if not eof:
            text = text[: -len(newline)]
        path = args.work / f"valid-{number}.csv"
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode())
        data = load_csv(path)
        assert (data.question_id, data.model, data.score) == (
            unambiguous.question_id,
            unambiguous.model,
            unambiguous.score,
        )
        result.setdefault("valid_csv", {})[path.name] = records_digest(data)

    root = Path(__file__).resolve().parents[2]
    retained = sorted((root / "examples").rglob("*.csv")) + [
        root / "studies/leaderboard-overlap/partial-cohorts.csv"
    ]
    for path in retained:
        data = load_csv(path)
        result.setdefault("retained_csv", {})[str(path.relative_to(root))] = {
            "records": len(data),
            "sha256": records_digest(data),
        }

    public_source = root / "studies/swe-bench-verified/data/outcomes.json"
    public = json.loads(public_source.read_text())
    ids = [submission["id"] for submission in public["submissions"][:2]]
    proc = subprocess.run(
        [sys.executable, str(root / "studies/swe-bench-verified/to_csv.py"), *ids], capture_output=True
    )
    assert proc.returncode == 0, proc.stderr
    public_csv = args.work / "swe-bench.csv"
    public_csv.write_bytes(proc.stdout)
    data = load_csv(public_csv)
    assert len(data) == 1000
    result["public_csv"] = {
        "source": public["source"],
        "ids": ids,
        "records": len(data),
        "input_sha256": hashlib.sha256(proc.stdout).hexdigest(),
        "records_sha256": records_digest(data),
    }

    invalid = {}
    for delimiter, name in [(",", "comma"), (";", "semicolon"), ("\t", "tab")]:
        header = delimiter.join(["question_id", "model", "score"]) + "\n"
        prefix = header + delimiter.join(["q1", "A", "1"]) + "\n"
        prefix += delimiter.join(["q1", "B", "0"]) + "\n" + delimiter.join(["q2", "A", "1"]) + "\n"
        for kind, tail, line in [
            ("unfinished", delimiter.join(["q2", "B", '"0']), 5),
            ("after-quote", delimiter.join(["q2", "B", '"0"0']), 5),
            ("multiline", '"q2\ncontinued' + delimiter + "B" + delimiter + "0", 6),
        ]:
            invalid[f"{name}-{kind}"] = (prefix + tail, line)
    invalid["unfinished-header"] = ('question_id,model,"score', 1)
    invalid["after-quote-header"] = ('question_id,model,"score"junk\nq1,A,1\n', 1)
    invalid["field-limit"] = ("question_id,model,score\n" + "q" * (csv.field_size_limit() + 1) + ",A,1\n", 2)
    for name, (text, line) in invalid.items():
        path = args.work / f"{name}.csv"
        path.write_text(text, encoding="utf-8")
        entry = capture(lambda path=path: asdict(load_csv(path)))
        entry["located_rejection"] = (
            not entry["accepted"]
            and entry["type"] == "ValueError"
            and f"{path}:{line}: invalid CSV" in entry["error"]
        )
        result["csv"][name] = entry
        commands = {
            "summarize": ["summarize", str(path), "--model", "A", "--json"],
            "compare": [
                "compare",
                str(path),
                "--model-a",
                "A",
                "--model-b",
                "B",
                "--json",
                "--html",
                str(args.work / "guard.html"),
            ],
            "leaderboard": ["leaderboard", str(path), "--json", "--plot", str(args.work / "guard.svg")],
            "import": ["import", "lm-eval", str(path), "-o", str(args.work / "guard.csv")],
        }
        for command, argv in commands.items():
            guards = [args.work / f"guard.{ext}" for ext in ["html", "svg", "csv"]]
            for guard in guards:
                guard.write_bytes(b"existing output must survive invalid input\n")
            proc = subprocess.run(
                [sys.executable, "-m", "errorbars.cli", *argv], text=True, capture_output=True
            )
            preserved = all(
                guard.read_bytes() == b"existing output must survive invalid input\n" for guard in guards
            )
            safe = (
                proc.returncode == 1
                and not proc.stdout
                and "Traceback" not in proc.stderr
                and f"{path}:{line}: invalid CSV" in proc.stderr
                and preserved
            )
            result["cli"][f"{name}/{command}"] = {
                "exit": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr.strip().splitlines()[-1] if proc.stderr else "",
                "traceback": "Traceback" in proc.stderr,
                "preserved": preserved,
                "safe_rejection": safe,
            }

    # Actual report and CLI JSON are also compared byte-for-byte before/after.
    valid = args.work / "valid-0.csv"
    report = args.work / "comparison.html"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "errorbars.cli",
            "compare",
            str(valid),
            "--model-a",
            "A",
            "--model-b",
            "B",
            "--json",
            "--html",
            str(report),
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    result["valid_cli"] = {
        "json_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "html_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "difference": json.loads(proc.stdout)["mean_diff"],
    }
    result["totals"] = {
        "duplicate_columns_rejected": sum(
            not v["accepted"]
            and v["type"] == "ValueError"
            and "duplicate DataFrame columns" in v["error"]
            and not v["warnings"]
            for v in result["dataframes"].values()
        ),
        "located_csv_rejections": sum(v["located_rejection"] for v in result["csv"].values()),
        "safe_cli_rejections": sum(v["safe_rejection"] for v in result["cli"].values()),
        "valid_csv": len(result["valid_csv"]),
        "valid_dataframes": len(result["valid_dataframes"]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False).replace(str(args.work), "<work>") + "\n"
    )
    print(json.dumps(result["totals"]))
    if not args.observe_only:
        assert result["totals"] == {
            "duplicate_columns_rejected": 8,
            "located_csv_rejections": 12,
            "safe_cli_rejections": 48,
            "valid_csv": 48,
            "valid_dataframes": 3,
        }


if __name__ == "__main__":
    main()
