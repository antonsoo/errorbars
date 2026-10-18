"""Write native Inspect logs from authored outcomes, without model calls.

The two scripted solvers differ in where successes occur across three attempts:
broad succeeds once on every question; concentrated succeeds on all attempts
for 18 of the 24 questions. Native reducers consequently answer different
questions. Files are copied verbatim from Inspect's own writer.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import tempfile
from pathlib import Path

from inspect_ai import Epochs, Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, match, mean, scorer
from inspect_ai.solver import solver


@solver
def scripted(profile):
    async def solve(state, generate):
        question = int(state.sample_id[1:])
        correct = state.epoch == 1 if profile == "broad" else question < 18
        state.output = ModelOutput.from_content("mockllm/model", "gold" if correct else "wrong")
        state.completed = True
        return state
    return solve


@scorer(metrics={"correct": [mean()], "loss": [mean()]})
def named_grade():
    async def score(state, target):
        correct = state.output.completion == target.text
        return Score(value={"correct": int(correct), "loss": int(not correct)})
    return score


def capture(destination):
    destination.mkdir(parents=True, exist_ok=True)
    observations = []
    reductions = ["mean", "max", ["mean", "max"], "pass_at_2", "median", "mode", "at_least_2", []]
    with tempfile.TemporaryDirectory(prefix="inspect-reducers-") as directory:
        for reduction in [*reductions, "named-max"]:
            named = reduction == "named-max"
            label = "-".join(reduction) if isinstance(reduction, list) else reduction
            label = label or "none"
            for profile in ("broad", "concentrated"):
                task = Task(
                    name=f"epoch_{profile}_{label}",
                    dataset=[Sample(id=f"q{i:02}", input=f"Authored question {i}: reply gold",
                                    target="gold") for i in range(24)],
                    solver=scripted(profile), scorer=named_grade() if named else match(),
                    epochs=Epochs(3, "max" if named else reduction),
                )
                log = eval(task, model="mockllm/model", log_dir=directory,
                           display="none", max_samples=1)[0]
                assert log.status == "success", log.error
                path = destination / f"{label}-{profile}.eval"
                shutil.copyfile(log.location, path)
                observations.append({
                    "file": path.name, "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "raw_samples": len(log.samples),
                    "config": log.eval.config.model_dump(exclude_none=True),
                    "results": [x.model_dump(mode="json", exclude_none=True) for x in log.results.scores],
                    "reductions": [{"scorer": x.scorer, "reducer": x.reducer, "samples": len(x.samples)}
                                   for x in log.reductions or []],
                })
                print(path.name, flush=True)
    manifest = {"synthetic": True, "inspect_ai": importlib.metadata.version("inspect-ai"),
                "model": "built-in mockllm; scripted solver; no model API",
                "questions": 24, "epochs": 3, "observations": observations}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    capture(parser.parse_args().destination)
