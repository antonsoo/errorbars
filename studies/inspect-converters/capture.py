"""Generate native Inspect logs with scripted answers and documented grade encodings."""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import tempfile
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    accuracy,
    mean,
    scorer,
    value_to_float,
)
from inspect_ai.solver import generate

ROOT = Path(__file__).resolve().parent
REVERSE = value_to_float(correct=0, incorrect=1)


@scorer(metrics=[accuracy(to_float=REVERSE)])
def reversed_grade():
    async def score(state, target):
        return Score(value=int(state.output.completion != target.text))
    return score


@scorer(metrics=[accuracy()])
def default_grade():
    async def score(state, target):
        return Score(value=CORRECT if state.output.completion == target.text else INCORRECT)
    return score


@scorer(metrics={"reversed": [accuracy(to_float=REVERSE)], "plain": [mean()]})
def named_grade():
    async def score(state, target):
        correct = state.output.completion == target.text
        return Score(value={"reversed": int(not correct), "plain": int(correct)})
    return score


def capture(destination):
    destination.mkdir(parents=True, exist_ok=True)
    samples = [Sample(id=f"q{i}", input=f"Synthetic question {i}: answer gold", target="gold")
               for i in range(8)]
    observations = []
    with tempfile.TemporaryDirectory(prefix="inspect-converters-") as directory:
        for encoding, factory in (("reversed", reversed_grade), ("default", default_grade),
                                  ("named", named_grade)):
            for label, answer in (("perfect", "gold"), ("wrong", "wrong")):
                model = get_model("mockllm/model", custom_outputs=[
                    ModelOutput.from_content("mockllm/model", answer) for _ in samples
                ])
                log = eval(Task(dataset=samples, solver=generate(), scorer=factory(),
                                name=f"{encoding}_{label}"), model=model,
                           log_dir=directory, display="none", max_samples=1)[0]
                assert log.status == "success", log.error
                path = destination / f"{encoding}-{label}.eval"
                shutil.copyfile(log.location, path)
                observations.append({"file": path.name, "status": log.status, "samples": len(log.samples),
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "native_results": [s.model_dump(mode="json")
                                                        for s in log.results.scores]})
    return {"synthetic": True, "inspect_ai": importlib.metadata.version("inspect-ai"),
            "model": "built-in mockllm; scripted answers; no model API",
            "observations": observations}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", nargs="?", type=Path, default=ROOT / "captures")
    args = parser.parse_args()
    result = capture(args.destination)
    (args.destination / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Captured {len(result['observations'])} successful native Inspect runs")
