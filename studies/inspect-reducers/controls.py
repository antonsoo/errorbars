"""Replay every other retained Inspect log and hash its canonical observations."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from errorbars.adapters.inspect_ai import load_inspect_log
from errorbars.io import write_csv

ROOT = Path(__file__).resolve().parents[2]
OWN = Path(__file__).resolve().parent


def replay(output):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        canonical = Path(directory) / "scores.csv"
        for path in sorted(ROOT.rglob("*.eval")):
            if OWN in path.parents or any(part.startswith(".") for part in path.relative_to(ROOT).parts):
                continue
            row = {"file": path.relative_to(ROOT).as_posix(),
                   "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            try:
                data = load_inspect_log(path)
                write_csv(data, canonical)
                row.update(status="loaded", observations=len(data),
                           canonical_sha256=hashlib.sha256(canonical.read_bytes()).hexdigest())
            except ValueError as exc:
                row.update(status="refused", error=str(exc))
            rows.append(row)
    output.write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"logs": len(rows), "loaded": sum(r["status"] == "loaded" for r in rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    replay(parser.parse_args().out)
