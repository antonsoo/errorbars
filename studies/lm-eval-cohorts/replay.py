"""Replay native captures and labelled damage controls through the actual CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "studies/lm-eval-cohorts"
FIXTURES = ROOT / "tests/fixtures"
TINY = next((FIXTURES / "lm_eval_output/sshleifer__tiny-gpt2").glob("samples_*.jsonl"))
SIDECAR = next(TINY.parent.glob("results_*.json"))
MULTIFILTER = next(FIXTURES.glob("samples_gsm8k_*.jsonl"))


def digest(path: Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def prepare(folder: Path, variant: str) -> tuple[Path, Path]:
    folder.mkdir()
    samples, sidecar = folder / TINY.name, folder / SIDECAR.name
    shutil.copyfile(TINY, samples)
    shutil.copyfile(SIDECAR, sidecar)
    rows = samples.read_text().splitlines()
    if variant == "prefix":
        samples.write_text("\n".join(rows[:5]) + "\n")
    elif variant == "correct-only":
        samples.write_text("\n".join(line for line in rows if json.loads(line)["acc"] == 1) + "\n")
    elif variant == "one-missing":
        samples.write_text("\n".join(rows[:-1]) + "\n")
    elif variant == "one-added":
        rows.append(json.dumps({**json.loads(rows[-1]), "doc_id": 999}))
        samples.write_text("\n".join(rows) + "\n")
    elif variant == "orphan":
        sidecar.unlink()
    elif variant == "foreign-count":
        sidecar.unlink()
        (folder / "results_2026-01-01T00-00-00.000000.json").write_text(
            '{"model_name":"foreign","n-samples":{"copa":{"effective":999}}}'
        )
    elif variant == "legacy-no-count":
        sidecar.write_text('{"model_name":"legacy"}')
    elif variant == "invalid-count":
        sidecar.write_text('{"model_name":"example","n-samples":{"copa":{"effective":true}}}')
    elif variant == "damaged-results":
        sidecar.write_text('{"model_name":')
    elif variant.startswith("filters"):
        samples.unlink()
        sidecar.unlink()
        samples = folder / MULTIFILTER.name
        shutil.copyfile(MULTIFILTER, samples)
        stamp = MULTIFILTER.name.split("_2026-", 1)[1].removesuffix(".jsonl")
        sidecar = folder / f"results_2026-{stamp}.json"
        sidecar.write_text(json.dumps({
            "model_name": "multifilter", "n-samples": {
                "gsm8k_cot_self_consistency": {"original": 100, "effective": 4},
            },
        }))
        if variant != "filters-complete":
            rows = samples.read_text().splitlines()
            removed = next(line for line in rows if json.loads(line)["filter"] == "maj@8")
            samples.write_text("\n".join(line for line in rows if line != removed) + "\n")
    return samples, sidecar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--src", type=Path, help="omit to use the installed wheel")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    interpreter = Path(os.path.abspath(args.python))
    env = {**os.environ, "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    if args.src:
        env["PYTHONPATH"] = str(args.src.resolve())
    cache = STUDY / "cache"
    cache.mkdir(exist_ok=True)
    definitions = [
        ("complete-inferred", "complete", "summarize", False, None, False),
        ("complete-explicit", "complete", "summarize", True, None, False),
        ("complete-directory", "complete", "directory", True, None, False),
        ("truncated-inferred", "prefix", "summarize", False, None, True),
        ("truncated-explicit", "prefix", "summarize", True, None, True),
        ("correct-only-explicit", "correct-only", "summarize", True, None, True),
        ("missing-compare", "one-missing", "compare", True, None, True),
        ("missing-leaderboard", "one-missing", "leaderboard", True, None, True),
        ("missing-import-preserves-output", "one-missing", "import", True, None, True),
        ("added-record", "one-added", "summarize", True, None, True),
        ("invalid-count", "invalid-count", "summarize", True, None, True),
        ("damaged-results", "damaged-results", "summarize", True, None, True),
        ("orphan-explicit", "orphan", "summarize", True, None, False),
        ("unrelated-count-ignored", "foreign-count", "summarize", True, None, False),
        ("legacy-no-count", "legacy-no-count", "summarize", False, None, False),
        ("filters-complete", "filters-complete", "summarize", False, "maj@8", False),
        ("selected-filter-missing", "filters-missing", "summarize", False, "maj@8", True),
        ("unselected-filter-missing", "filters-missing", "summarize", False, "score-first", False),
        ("sidecar-output-explicit", "complete", "export-sidecar", True, None, True),
        ("sidecar-hardlink-explicit", "complete", "export-hardlink", True, None, True),
    ]
    cases = []
    with tempfile.TemporaryDirectory(prefix="cohort-", dir=cache) as temporary:
        work = Path(temporary)
        work_prefix = str(work.relative_to(ROOT))
        normalize = lambda value: value.replace(work_prefix, "<work>")  # noqa: E731
        complete, _ = prepare(work / "control", "complete")
        for label, variant, kind, named, filter_name, rejects in definitions:
            folder = work / label
            samples, sidecar = prepare(folder, variant)
            rel = lambda p: str(p.relative_to(ROOT))  # noqa: E731
            spec = f"example={rel(samples)}" if named else rel(samples)
            output = folder / "export.csv"
            message = "cohort mismatch"
            if kind in ("import", "export-sidecar", "export-hardlink"):
                if kind == "export-sidecar":
                    output = sidecar
                elif kind == "export-hardlink":
                    output.hardlink_to(sidecar)
                else:
                    output.write_bytes(b"previous complete export\n")
                argv = ["import", "lm-eval", spec, "-o", rel(output)]
                if kind.startswith("export-"):
                    message = "output must not replace an input file"
            elif kind in ("compare", "leaderboard"):
                argv = [kind, f"control={rel(complete)}", spec, "--json"]
            elif kind == "directory":
                argv = ["summarize", f"example={rel(folder)}", "--json"]
            else:
                argv = ["summarize", spec, "--json"]
            if filter_name:
                argv += ["--filter", filter_name]
            if variant == "invalid-count":
                message = "'effective' must be a positive integer"
            elif variant == "damaged-results":
                message = "invalid matching lm-eval results"
            before = {str(p.relative_to(folder)): digest(p) for p in folder.iterdir() if p.is_file()}
            process = subprocess.run(
                [str(interpreter), "-m", "errorbars.cli", *argv], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=20, check=False,
            )
            after = {str(p.relative_to(folder)): digest(p) for p in folder.iterdir() if p.is_file()}
            payload = json.loads(process.stdout) if process.returncode == 0 and "--json" in argv else None
            if rejects:
                agrees = (process.returncode == 1 and not process.stdout and before == after
                          and message in process.stderr)
            else:
                count = 4 if variant.startswith("filters") else 20
                mean = 0 if count == 4 else 0.6
                agrees = (process.returncode == 0 and payload is not None and payload["n"] == count
                          and payload["mean"] == mean and before == after)
            # Preserve unedited content while replacing only the disposable path prefix.
            cases.append({
                "case": label, "derivation": variant,
                "command": ["errorbars", *(normalize(value) for value in argv)],
                "expected": "reject without modifying evidence/output" if rejects else "accept",
                "exit_code": process.returncode, "stdout": normalize(process.stdout),
                "stderr": normalize(process.stderr), "before": before, "after": after,
                "agrees": agrees,
            })
    info = subprocess.check_output([
        str(interpreter), "-c",
        "import json,platform,importlib.metadata as m; "
        "print(json.dumps({'python':platform.python_version(),'numpy':m.version('numpy')}))",
    ], text=True, env=env)
    result = {
        "environment": json.loads(info), "source_override": args.src is not None,
        "native_inputs": {str(p.relative_to(ROOT)): digest(p) for p in (TINY, SIDECAR, MULTIFILTER)},
        "population": "native 20-question COPA / 4-question, 3-filter GSM8K software import checks",
        "controls": "Damage is derived; the multi-filter count sidecar is constructed, not a native capture.",
        "cases": cases, "count": len(cases), "disagreements": sum(not row["agrees"] for row in cases),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(cases)} CLI workflows, {result['disagreements']} disagreements")
    if result["disagreements"] and not args.observe_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
