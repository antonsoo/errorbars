"""Run real CLI exports under a fixed Linux memory ceiling, then check every pair."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import resource
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from fractions import Fraction
from functools import cache
from pathlib import Path

from cases import write_case


@cache
def exact_discordance_p(wins: int, losses: int) -> Fraction:
    n = wins + losses
    return min(Fraction(1), Fraction(2 * sum(math.comb(n, j) for j in range(min(wins, losses) + 1)), 2**n))


def verify_report(path: Path, report: dict, pairs: int) -> dict:
    scores: dict[str, list[int]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            scores.setdefault(row["model"], []).append(int(row["score"]))
    tests = report["pairwise"]
    assert len(tests) == math.comb(2 * pairs, 2)
    raw = []
    for test in tests:
        a, b = scores[test["model_a"]], scores[test["model_b"]]
        wins = sum(left > right for left, right in zip(a, b, strict=True))
        losses = sum(left < right for left, right in zip(a, b, strict=True))
        raw.append(exact_discordance_p(wins, losses))
        assert test["test"] == "mcnemar_exact"
        assert abs(test["p_value_used"] - float(raw[-1])) < 1e-12
    previous = Fraction(0)
    for rank, index in enumerate(sorted(range(len(raw)), key=lambda i: raw[i])):
        adjusted = min(Fraction(1), max(previous, raw[index] * (len(raw) - rank)))
        previous = adjusted
        assert abs(tests[index]["p_holm"] - float(adjusted)) < 1e-12
        same_pair = tests[index]["model_a"][:7] == tests[index]["model_b"][:7]
        assert (adjusted < Fraction(1, 20)) == same_pair
    assert len(report["entries"]) == 2 * pairs
    for entry in report["entries"]:
        assert entry["mean"] == sum(scores[entry["model"]]) / 1024
        assert entry["n"] == 1024
    assert report["untested_pairs"] == []
    for row in report["rank_comparisons"].values():
        assert len(row["significant"]) == 1
        assert len(row["non_significant"]) == 2 * pairs - 2
        assert row["untested"] == []
    if pairs <= 12:
        assert len(report["groups"]) == 2**pairs
        # Every complete group chooses one and only one member from each pair.
        assert len({tuple(group) for group in report["groups"]}) == 2**pairs
        for group in report["groups"]:
            assert len(group) == pairs
            assert {name[:7] for name in group} == {f"pair-{i:02}" for i in range(1, pairs + 1)}
    else:
        assert report["groups"] is None
        assert report["group_status"] == "omitted_group_limit"
        assert report["group_limits"] == {"max_groups": 4096, "max_search_states": 50000}
        assert len(report["warnings"]) == 1
    return {"pairwiseExactRationalChecks": len(tests), "models": 2 * pairs,
            "mathematicalMaximalGroups": 2**pairs, "groupStatus": report.get("group_status", "complete")}


def limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--source", type=Path,
                        help="Optional source package root; omit for an installed wheel")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--small-only", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", NO_COLOR="1", COLUMNS="120")
    env.pop("PYTHONPATH", None)
    if args.source:
        env["PYTHONPATH"] = str(args.source.resolve() / "src")
    # Preserve the venv executable path: resolving its symlink loses that venv.
    python = str(args.python.absolute())
    isolate = [] if args.source else ["-I"]
    results = []
    for pairs in ([8, 12] if args.small_only else [8, 12, 25]):
        path = args.out / f"pairs-{pairs}.csv"
        write_case(path, pairs)
        formats = ["json", "terminal"] if pairs == 25 else ["json"]
        for fmt in formats:
            name = f"pairs-{pairs}-{fmt}"
            output, errors, usage = [args.out / (name + suffix) for suffix in [".stdout", ".stderr", ".time"]]
            svg = args.out / (name + ".svg")
            args_cli = ["--json"] if fmt == "json" else ["--plot", str(svg)]
            command = ["/usr/bin/time", "-f", '{"seconds":%e,"peakRssKiB":%M,"exit":%x}',
                       "-o", str(usage), python, *isolate, "-m", "errorbars.cli", "leaderboard",
                       str(path), *args_cli]
            started = time.perf_counter()
            with output.open("w") as stdout, errors.open("w") as stderr:
                child = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env,
                                         preexec_fn=limits, start_new_session=True)
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    raise
            assert child.returncode == 0, errors.read_text()
            assert errors.read_bytes() == b""
            content = output.read_bytes()
            if fmt == "json":
                report = json.loads(content)
                checked = verify_report(path, report, pairs)
                report.pop("group_status", None)
                normalized = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
                checked["reportSha256WithoutGroupStatus"] = hashlib.sha256(normalized).hexdigest()
            else:
                assert "groups were omitted" in content.decode()
                assert "1,225" in content.decode() or "1225" in content.decode()
                plot = ET.fromstring(svg.read_bytes())
                assert plot.tag == "{http://www.w3.org/2000/svg}svg"
                # The plot prefixes visible model names with their numeric rank.
                labels = {(node.text or "").partition(". ")[2]
                          for node in plot.iter("{http://www.w3.org/2000/svg}text")}
                assert {f"pair-{i:02}-{side}" for i in range(1, pairs + 1)
                        for side in ["base", "edit"]} <= labels
                checked = {"svgSha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
                           "svgBytes": svg.stat().st_size, "allModelsInSvg": True,
                           "terminalExplainsOmission": True}
            result = {"case": name, "inputBytes": path.stat().st_size,
                      "inputSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "exit": child.returncode, "seconds": time.perf_counter() - started,
                      "resource": json.loads(usage.read_text().splitlines()[-1]),
                      "outputSha256": hashlib.sha256(content).hexdigest(), **checked}
            results.append(result)
            print(json.dumps(result), flush=True)
    receipt = {"harnessPython": platform.python_version(), "cliPython": subprocess.check_output(
        [python, "--version"], text=True).strip(), "results": results,
        "addressSpaceLimitMiB": 512, "outputLimitMiB": 8,
        "note": ("Single CLI observations under Linux limits; not production timing estimates. "
                 "Every pair uses integer binomial tails and rational Holm correction.")}
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
