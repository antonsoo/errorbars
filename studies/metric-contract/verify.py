"""Exercise actual installed CLI imports, ranking, refused exports and report payloads.

Only the package's runtime dependencies are needed. Use an absolute script path
from outside a source tree with a fresh wheel environment for artifact checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import errorbars.io
from errorbars.inputs import load_inputs
from errorbars.io import load_csv
from errorbars.leaderboard import build_leaderboard

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
        work = Path(temporary).resolve()

        def command(label: str, arguments: list[str], *, success: bool = True) -> subprocess.CompletedProcess:
            result = subprocess.run(
                [sys.executable, "-m", "errorbars.cli", *arguments],
                cwd=work, capture_output=True, text=True, check=False,
            )
            assert "Traceback" not in result.stderr, result.stderr
            assert result.returncode == (0 if success else 1), (label, result.stderr)
            if not success:
                assert not result.stdout, (label, result.stdout)
            cases.append({"case": label, "exit": result.returncode, "no_traceback": True})
            return result

        specs = [str(HERE / "captures" / name) for name in ("precise", "noisy")]
        board_result = command("native lower loss", ["leaderboard", *specs, "--metric", "mean_nll",
                                                     "--json", "--plot", str(work / "loss.svg")])
        board = json.loads(board_result.stdout)
        assert [e["model"] for e in board["entries"]] == ["precise", "noisy"]
        assert board["higher_is_better"] is False and board["direction_source"] == "recorded"
        assert [e["mean"] for e in board["entries"]] == [0.25, 0.790625]
        assert math.isclose(board["pairwise"][0]["mean_diff"], -0.540625, rel_tol=1e-14)
        assert "lower scores first (recorded)" in (work / "loss.svg").read_text()
        terminal = command("terminal direction", ["leaderboard", *specs, "--metric", "mean_nll"])
        assert "lower scores first (recorded)" in terminal.stdout
        (work / "loss-terminal.txt").write_text(terminal.stdout)
        (work / "loss.json").write_text(board_result.stdout)
        high = command("native higher likelihood", [
            "leaderboard", *specs, "--metric", "likelihood", "--json",
        ])
        assert json.loads(high.stdout)["higher_is_better"] is True
        assert json.loads(high.stdout)["entries"][0]["model"] == "precise"

        canonical = work / "loss.csv"
        command("native CSV export", [
            "import", "lm-eval", *specs, "--metric", "mean_nll", "-o", str(canonical),
        ])
        data = load_csv(canonical)
        assert data.higher_is_better == [False] * 64
        assert build_leaderboard(data).entries[0].model == "precise"
        roundtrip = command("CSV leaderboard", ["leaderboard", str(canonical), "--json"])
        assert json.loads(roundtrip.stdout) == board
        renamed = command("named native inputs", ["leaderboard", f"A={specs[0]}", f"B={specs[1]}",
                                                   "--metric", "mean_nll", "--json"])
        assert json.loads(renamed.stdout)["entries"][0]["model"] == "A"

        report = work / "loss.html"
        compared = command("native offline comparison", ["compare", *specs, "--metric", "mean_nll",
                                                           "--html", str(report), "--json"])
        match = re.search(r'<script[^>]+id="report-data"[^>]*>(.*?)</script>', report.read_text(), re.S)
        assert match is not None
        payload = json.loads(match[1])
        assert payload["comparison"]["mean_diff"] == json.loads(compared.stdout)["mean_diff"]
        assert all(obs["higher_is_better"] is False for q in payload["questions"]
                   for obs in q["observations_a"] + q["observations_b"])

        plot = work / "preserve.svg"
        for paths in (specs, [str(canonical)]):
            plot.write_text("keep this previous plot\n")
            refused = command("contradictory override", ["leaderboard", *paths, "--metric", "mean_nll",
                                                          "--score-direction", "higher", "--json",
                                                          "--plot", str(plot)], success=False)
            assert "conflicts with recorded" in refused.stderr
            assert plot.read_text() == "keep this previous plot\n"

        unknown = work / "unknown.csv"
        unknown.write_text("question_id,model,score\nq1,A,0.2\nq2,A,0.3\nq1,B,0.6\nq2,B,0.8\n")
        default = command("unknown direction labelled default", ["leaderboard", str(unknown), "--json"])
        assert json.loads(default.stdout)["direction_source"] == "default"
        explicit = command("explicit lower raw scores", ["leaderboard", str(unknown),
                                                          "--score-direction", "lower", "--json"])
        assert json.loads(explicit.stdout)["entries"][0]["model"] == "A"
        assert json.loads(explicit.stdout)["direction_source"] == "explicit"

        for operation in ("summarize", "compare", "leaderboard", "import"):
            destination = work / ("preserve.csv" if operation == "import" else
                                  "preserve.html" if operation == "compare" else "preserve.svg")
            destination.write_text("keep the previous artifact\n")
            arguments = [operation, *(["lm-eval"] if operation == "import" else []),
                         *([specs[0]] if operation == "summarize" else specs), "--metric", "perplexity"]
            if operation == "import":
                arguments.extend(["-o", str(destination)])
            elif operation == "compare":
                arguments.extend(["--html", str(destination), "--json"])
            elif operation == "leaderboard":
                arguments.extend(["--plot", str(destination), "--json"])
            result = command("refuse nonlinear " + operation, arguments, success=False)
            assert "not an arithmetic mean" in result.stderr
            assert destination.read_text() == "keep the previous artifact\n"

        # Model naming cannot replace or contradict recorded metric semantics.
        source = next((HERE / "captures/precise").rglob("samples_*.jsonl"))
        samples = work / source.name
        shutil.copyfile(source, samples)
        sidecar = next(source.parent.glob("results_*.json"))
        metadata = json.loads(sidecar.read_text())
        metadata["configs"]["metric_contract"]["metric_list"][0]["aggregation"] = "nanmean"
        (work / sidecar.name).write_text(json.dumps(metadata))
        finite_mean = command("finite nanmean aggregation", [
            "leaderboard", f"A={samples}", specs[1], "--metric", "mean_nll", "--json",
        ])
        assert json.loads(finite_mean.stdout)["entries"][0]["mean"] == 0.25
        metadata["higher_is_better"]["metric_contract"]["mean_nll"] = True
        (work / sidecar.name).write_text(json.dumps(metadata))
        result = command("conflicting native declarations", [
            "leaderboard", f"A={samples}", specs[1], "--metric", "mean_nll", "--json",
        ], success=False)
        assert "conflicting higher_is_better" in result.stderr

        before = json.loads((HERE / "results/before.json").read_text())
        original = load_inputs(specs, metric="mean_nll").data
        assert original.score[:32] == [0.1, 0.2, 0.3, 0.4] * 8
        assert board["entries"][0]["mean"] == before["cases"][0]["errorbars_means"]["precise"]
        if args.artifacts:
            args.artifacts.mkdir(parents=True, exist_ok=True)
            for filename in ("loss.csv", "loss.json", "loss.svg", "loss.html", "loss-terminal.txt"):
                shutil.copyfile(work / filename, args.artifacts / filename)
        result = {
            "python": platform.python_version(), "numpy": np.__version__,
            "io_sha256": hashlib.sha256(Path(errorbars.io.__file__).read_bytes()).hexdigest(),
            "checks": cases, "cli_workflows": len(cases),
            "native_losses": board["entries"], "pairwise": board["pairwise"],
            "original_scores_retained": True,
        }
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"cli_workflows": len(cases), "python": result["python"], "numpy": result["numpy"]}))


if __name__ == "__main__":
    main()
