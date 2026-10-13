"""Run actual CLI exports in disposable directories and compare input/output bytes.

Requires POSIX for symlinks, hard links, FIFOs and RLIMIT_FSIZE fault injection.
Pass --source /checkout/src for a source replay; omit it for an installed wheel.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCORES = ROOT / "examples/data/reading_comprehension.csv"
NATIVE = ROOT / "tests/fixtures/samples_copa_2026-09-24T03-04-37.941131.jsonl"
STAMP = "2026-09-24T03-04-37.941131"
PREVIOUS = b"previous complete export\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(folder: Path) -> dict:
    """Do not follow links or open a FIFO when checking retained filesystem state."""
    result = {}
    for path in sorted(folder.rglob("*")):
        key = str(path.relative_to(folder))
        if path.is_symlink():
            result[key] = {"symlink": os.readlink(path)}
        elif path.is_file():
            data = path.read_bytes()
            result[key] = {"bytes": len(data), "sha256": sha(data)}
        elif not path.is_dir():
            result[key] = {"mode": path.stat().st_mode}
    return result


def limit_file_size() -> None:
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024, 1024))


def command(kind: str, source: Path, output: Path, *, infer: bool = False) -> list[str]:
    if kind == "csv":
        return ["import", "lm-eval", str(source), "-o", str(output),
                *([] if infer else ["--model", "example"])]
    if kind == "svg":
        return ["leaderboard", str(source), "--plot", str(output), "--json"]
    return ["compare", str(source), "--model-a", "tuned-70b", "--model-b", "baseline-70b",
            "--html", str(output), "--json"]


def prepare(folder: Path, kind: str, variant: str) -> tuple[Path, Path, bool]:
    source = folder / (NATIVE.name if kind == "csv" else "scores.csv")
    shutil.copyfile(NATIVE if kind == "csv" else SCORES, source)
    output = folder / f"export.{kind}"
    infer = False
    if variant == "same-source":
        output = source
    elif variant == "canonical-source":
        source.unlink()
        source = folder / "scores.csv"
        shutil.copyfile(SCORES, source)
        output = source
    elif variant == "empty-source":
        source.unlink()
        source = folder / "empty.csv"
        source.write_bytes(b"question_id,model,score\n")
        output = source
    elif variant == "input-link":
        source.rename(output)
        source.symlink_to(output.name)
    elif variant == "input-parent-link":
        real = folder / "real"
        real.mkdir()
        source.rename(real / source.name)
        alias = folder / "alias"
        alias.symlink_to("real", target_is_directory=True)
        source = alias / source.name
        output = real / source.name
    elif variant == "output-link":
        output.symlink_to(source.name)
    elif variant == "dangling-link":
        output.symlink_to("missing-target")
    elif variant == "hard-link":
        output.hardlink_to(source)
    elif variant in ("metadata", "metadata-link"):
        metadata = folder / f"results_{STAMP}.json"
        metadata.write_text('{"model_name":"example"}\n')
        infer = True
        if variant == "metadata":
            output = metadata
        else:
            metadata.rename(output)
            metadata.symlink_to(output.name)
    elif variant in ("replace", "write-failure"):
        output.write_bytes(PREVIOUS)
    elif variant == "long-name":
        output = folder / ("x" * (255 - len(kind) - 1) + "." + kind)
    elif variant == "parent-link":
        real = folder / "real"
        real.mkdir()
        alias = folder / "alias"
        alias.symlink_to("real", target_is_directory=True)
        output = alias / output.name
    elif variant == "directory":
        output.mkdir()
    elif variant == "fifo":
        os.mkfifo(output)
    elif variant != "new":
        raise AssertionError(variant)
    return source, output, infer


def validate_export(kind: str, data: bytes) -> None:
    if kind == "csv":
        rows = list(csv.DictReader(io.StringIO(data.decode())))
        native = [json.loads(line) for line in NATIVE.read_text().splitlines()]
        assert len(rows) == len(native) and all(row["model"] == "example" for row in rows)
        assert [float(row["score"]) for row in rows] == [row["acc"] for row in native]
        assert [row["question_id"] for row in rows] == [f"copa-{row['doc_id']}" for row in native]
    elif kind == "svg":
        assert ET.fromstring(data).tag == "{http://www.w3.org/2000/svg}svg"
        assert b"baseline-70b" in data and b"tuned-70b" in data
    else:
        assert b"errorbars-comparison" in data and b"Content-Security-Policy" in data
        assert b"baseline-70b" in data and b"tuned-70b" in data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--python", required=True, type=Path)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--work", required=True, type=Path)
    args = ap.parse_args()
    # Make it independent of child cwd without resolving a venv's Python symlink.
    args.python = Path(os.path.abspath(args.python))
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if args.source:
        env["PYTHONPATH"] = str(args.source.resolve())
    cases = [(kind, variant) for kind in ("csv", "svg", "html") for variant in (
        "input-link", "output-link", "dangling-link", "hard-link", "write-failure",
        "new", "replace", "long-name", "parent-link",
    )] + [
        ("csv", "same-source"), ("svg", "same-source"), ("csv", "canonical-source"),
        ("csv", "empty-source"), ("svg", "input-parent-link"), ("csv", "metadata"),
        ("csv", "metadata-link"), ("svg", "directory"), ("svg", "fifo"),
    ]
    args.work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="replay-", dir=args.work) as temporary:
        work = Path(temporary)
        for kind, variant in cases:
            folder = work / f"{kind}-{variant}"
            folder.mkdir()
            source, output, infer = prepare(folder, kind, variant)
            before = snapshot(folder)
            expected = "written" if variant in ("new", "replace", "long-name", "parent-link") else "rejected"
            argv = command(kind, source, output, infer=infer)
            try:
                process = subprocess.run(
                    [str(args.python), "-m", "errorbars.cli", *argv], cwd=folder, env=env,
                    capture_output=True, timeout=10,
                    preexec_fn=limit_file_size if variant == "write-failure" else None,
                )
                exit_code, stdout, stderr = process.returncode, process.stdout, process.stderr
            except subprocess.TimeoutExpired:
                exit_code, stdout, stderr = None, b"", b"timed out"
            after = snapshot(folder)
            normalized_error = stderr.decode().replace(str(folder), "<case>")
            leftover = list(folder.rglob(".errorbars-output-*.tmp"))
            agrees = False
            export = None
            if expected == "rejected":
                reasons = {
                    "write-failure": ("File too large",),
                    "empty-source": ("no rows found",),
                    "directory": ("Is a directory", "output must be a regular file"),
                }.get(variant, ("output must",))
                agrees = (exit_code == 1 and stdout == b"" and before == after
                          and any(reason in normalized_error for reason in reasons))
            elif exit_code == 0 and output.is_file():
                data = output.read_bytes()
                validate_export(kind, data)
                export = {"bytes": len(data), "sha256": sha(data)}
                # New exports may change only their destination; original inputs stay identical.
                changed = {key for key in before if before[key] != after.get(key)}
                agrees = changed <= {str(output.relative_to(folder))} and not leftover
            records.append({
                "case": folder.name, "expected": expected, "exit": exit_code,
                "stdoutBytes": len(stdout), "stderr": normalized_error.strip(),
                "before": before, "after": after, "unchanged": before == after,
                "export": export, "agrees": agrees,
            })
    print(json.dumps({
        "label": args.label,
        "python": subprocess.check_output([str(args.python), "--version"], text=True).strip(),
        "inputs": {str(p.relative_to(ROOT)): {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                   for p in (SCORES, NATIVE)},
        "cases": records, "count": len(records), "disagreements": sum(not row["agrees"] for row in records),
    }, indent=2))


if __name__ == "__main__":
    main()
