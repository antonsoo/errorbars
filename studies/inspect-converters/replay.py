"""Compare the native harness results to Errorbars' import and actual CLI behavior."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from inspect_ai.log import read_eval_log

from errorbars.inputs import load_inputs
from errorbars.leaderboard import build_leaderboard

ROOT = Path(__file__).resolve().parent


def replay():
    observations = []
    for encoding, score_key in (("reversed", None), ("default", None),
                                ("named", "reversed"), ("named", "plain")):
        refused = encoding == "reversed" or score_key == "reversed"
        paths = [ROOT / "captures" / f"{encoding}-{label}.eval" for label in ("perfect", "wrong")]
        item = {"encoding": encoding, "score_key": score_key, "expect_refusal": refused,
                "inputs": [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                           for p in paths]}
        native = []
        for path in paths:
            log = read_eval_log(path)
            native.append([r.model_dump(mode="json") for r in log.results.scores
                           if score_key is None or r.name == score_key])
        item["native_results"] = native
        try:
            data = load_inputs([f"perfect={paths[0]}", f"wrong={paths[1]}"], score_key=score_key).data
            board = build_leaderboard(data)
            item["accepted"] = True
            item["entries"] = [{"model": e.model, "mean": e.mean} for e in board.entries]
            item["first_rank"] = board.entries[0].model
        except ValueError as exc:
            item["accepted"] = False
            item["error"] = str(exc).replace(str(ROOT), "<study>")
        commands = []
        with tempfile.TemporaryDirectory(prefix="errorbars-converter-replay-") as directory:
            directory = Path(directory)
            for command in ("summarize", "compare", "leaderboard", "import"):
                suffix = {"compare": "html", "leaderboard": "svg"}.get(command, "csv")
                output = directory / f"{command}.{suffix}"
                output.write_bytes(b"previous output must survive\n")
                args = [sys.executable, "-m", "errorbars.cli", command]
                if command == "import":
                    args += ["inspect", str(paths[0]), "-o", str(output)]
                else:
                    args += [str(paths[0])] if command == "summarize" else [
                        f"perfect={paths[0]}", f"wrong={paths[1]}"
                    ]
                    args += ["--json"]
                    if command == "compare":
                        args += ["--html", str(output)]
                    elif command == "leaderboard":
                        args += ["--plot", str(output)]
                if score_key is not None:
                    args += ["--score-key", score_key]
                result = subprocess.run(args, text=True, capture_output=True)
                commands.append({"command": command, "exit": result.returncode,
                                 "stdout": result.stdout,
                                 "stderr": result.stderr.replace(str(ROOT), "<study>"),
                                 "previous_export_preserved": (
                                     output.read_bytes() == b"previous output must survive\n"
                                     if command != "summarize" else None)})
        item["commands"] = commands
        observations.append(item)
    return {"synthetic": True, "cases": len(observations),
            "wrong_acceptances": sum(o["expect_refusal"] and o["accepted"] for o in observations),
            "valid_controls": sum(not o["expect_refusal"] and o["accepted"] for o in observations),
            "observations": observations}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print({k: v for k, v in result.items() if k != "observations"})
    if args.check:
        assert result["wrong_acceptances"] == 0
        assert result["valid_controls"] == 2
        for case in result["observations"]:
            for command in case["commands"]:
                assert command["exit"] == int(case["expect_refusal"]), command
                if case["expect_refusal"]:
                    assert not command["stdout"] and "custom score conversion" in command["stderr"]
                    if command["command"] != "summarize":
                        assert command["previous_export_preserved"]
