"""Record synthetic responses under real Inspect scoring rules, without model APIs.

    uv run python examples/inspect-scoring/capture.py OUTPUT_DIRECTORY
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
from inspect_ai.scorer import includes, match
from inspect_ai.solver import generate


def capture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"inspect_ai": inspect_ai.__version__, "synthetic": True, "runs": {}}
    for name, scorer, improved in [
        ("exact", match(location="exact"), False),
        ("anywhere", match(location="any"), False),
        ("includes", includes(), False),
        ("exact-repeat", match(location="exact"), False),
        ("improved-exact", match(location="exact"), True),
    ]:
        samples = [
            Sample(id=f"q{i:02d}", input=f"What is {i} plus {i}?", target=str(2 * i))
            for i in range(1, 25)
        ]

        def respond(messages, tools, tool_choice, config, *, improved=improved):
            question = next(message.text for message in messages if message.role == "user")
            number = int(re.search(r"What is (\d+)", question).group(1))
            answer = str(2 * number)
            if number % 3 == 1 and not improved:
                answer = f"The answer is {answer}."
            elif number % 3 == 2:
                answer = "I do not know."
            return ModelOutput.from_content(model="mockllm/model", content=answer)

        log = eval(
            Task(name="scoring_identity", dataset=samples, solver=generate(), scorer=scorer),
            model=get_model("mockllm/model", custom_outputs=respond),
            log_dir=str(output / "raw"), display="none",
        )[0]
        assert log.status == "success", log.error
        target = output / f"{name}.eval"
        shutil.copyfile(log.location, target)
        recorded = read_eval_log(target)
        manifest["runs"][name] = {
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "results": recorded.results.model_dump(),
            "scorers": [scorer.model_dump() for scorer in recorded.eval.scorers],
            "observations": {
                sample.id: {"output": sample.output.completion,
                            "scores": {key: score.value for key, score in sample.scores.items()}}
                for sample in sorted(recorded.samples, key=lambda sample: sample.id)
            },
        }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(manifest['runs'])} controlled runs in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    capture(parser.parse_args().output)
