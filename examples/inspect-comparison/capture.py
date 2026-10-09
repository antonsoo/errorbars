"""Record controlled Inspect runs with the real local mockllm provider.

All questions and responses are synthetic; these are importer examples, not
measurements of model quality. No API key or network model call is needed.

    uv run python examples/inspect-comparison/capture.py OUTPUT_DIRECTORY
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
from inspect_ai.model import ChatMessageUser, ModelOutput, get_model
from inspect_ai.scorer import match
from inspect_ai.solver import generate, system_message


def capture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"inspect_ai": inspect_ai.__version__, "synthetic": True, "runs": {}}
    for name, operation, perfect, options in [
        ("original", "+", True, {}),
        ("solver-variant", "+", False, {}),
        ("different-questions", "*", False, {}),
        ("limited", "+", False, {"limit": (5, 17)}),
        ("selected-epochs", "+", False, {"sample_id": ["q02", "q05", "q09"], "epochs": 2}),
    ]:
        samples = [Sample(
            id=f"q{i:02d}", input=[ChatMessageUser(content=f"What is {i} {operation} {i}?")],
            target=str(i + i if operation == "+" else i * i),
        ) for i in range(1, 25)]

        def respond(messages, tools, tool_choice, config, *, perfect=perfect):
            question = next(message.text for message in messages if message.role == "user")
            number, operator = re.search(r"(\d+) ([+*])", question).groups()
            number = int(number)
            answer = number * 2 if operator == "+" else number * number
            if not perfect and number % 3 != 0:
                answer += 1
            return ModelOutput.from_content(model="mockllm/model", content=str(answer))

        model = get_model("mockllm/model", custom_outputs=respond)
        solvers = [generate()]
        if name == "solver-variant":
            solvers.insert(0, system_message("Return only the numeric answer."))
        task = Task(name="arithmetic_identity", dataset=samples, solver=solvers, scorer=match())
        log = eval(task, model=model, log_dir=str(output / "raw"), display="none", **options)[0]
        assert log.status == "success", log.error
        target = output / f"{name}.eval"
        shutil.copyfile(log.location, target)
        recorded = read_eval_log(target)
        manifest["runs"][name] = {
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "planned": recorded.results.total_samples,
            "completed": recorded.results.completed_samples,
            "recorded": len(recorded.samples),
            "question_ids": sorted({sample.id for sample in recorded.samples}),
            "scores": [sample.scores["match"].value for sample in recorded.samples],
        }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(manifest['runs'])} controlled runs in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    capture(parser.parse_args().output)
