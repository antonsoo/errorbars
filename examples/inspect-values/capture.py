"""Capture named grades from controlled responses through the real Inspect runner.

No model APIs or external datasets. Re-run into a new directory; retained logs
are original SDK outputs with synthetic responses, not model-quality evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import inspect_ai
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate


@scorer(metrics={"correct": [accuracy(), stderr()], "concise": [accuracy()], "words": [mean()]})
def answer_dimensions(max_words: int = 2):
    async def grade(state: TaskState, target: Target) -> Score:
        answer = state.output.completion.strip()
        return Score(value={
            "correct": CORRECT if answer == target.text else INCORRECT,
            "concise": len(answer.split()) <= max_words,
            "words": len(answer.split()),
        })
    return grade


def capture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"inspect_ai": inspect_ai.__version__, "synthetic": True, "runs": {}}
    for name, epochs in [("baseline", 1), ("candidate", 1), ("candidate-epochs", 2)]:
        def respond(messages, tools, tool_choice, config, *, variant=name):
            text = next(message.text for message in messages if message.role == "user")
            number = int(re.search(r"What is (\d+)", text).group(1))
            answer = str(2 * number)
            if variant == "baseline" and number % 3 != 0:
                answer = f"The answer is {answer}."
            elif variant != "baseline" and number % 3 == 2:
                answer = "unknown"
            return ModelOutput.from_content(model="mockllm/model", content=answer)

        log = eval(Task(
            name="named_score_dimensions", dataset=[
                Sample(id=f"q{i:02d}", input=f"What is {i} plus {i}?", target=str(2 * i))
                for i in range(1, 25)
            ], solver=generate(), scorer=answer_dimensions(),
        ), model=get_model("mockllm/model", custom_outputs=respond), epochs=epochs,
            log_dir=str(output / "raw"), display="none")[0]
        assert log.status == "success", log.error
        path = output / f"{name}.eval"
        shutil.copyfile(log.location, path)
        saved = read_eval_log(path)
        manifest["runs"][name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "epochs": epochs, "samples": len(saved.samples), "results": saved.results.model_dump(),
            "observations": [{"id": s.id, "epoch": s.epoch, "response": s.output.completion,
                              "target": s.target, "value": s.scores["answer_dimensions"].value}
                             for s in saved.samples],
        }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['runs'])} synthetic Inspect runs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    capture(parser.parse_args().output)
