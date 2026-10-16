"""Record constant fractional grades under one and three actual Inspect epochs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import Score, mean, scorer
from inspect_ai.solver import generate


@scorer(metrics=[mean()])
def fractional_grade():
    async def score(state, target):
        return Score(value=0.1)

    return score


def capture(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("capture destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    samples = [Sample(id=f"q{i:02}", input=f"Controlled question {i}", target="answer") for i in range(20)]
    records = []
    for epochs in (1, 3):
        model = get_model(
            "mockllm/model",
            custom_outputs=[ModelOutput.from_content("mockllm/model", "answer") for _ in range(20 * epochs)],
        )
        log = eval(
            Task(
                name="identical_fractional_grades",
                dataset=samples,
                solver=generate(),
                scorer=fractional_grade(),
            ),
            model=model,
            epochs=epochs,
            log_dir=str(destination / "raw"),
            display="none",
        )[0]
        assert log.status == "success", log.error
        assert len(log.samples) == 20 * epochs
        assert all(s.scores["fractional_grade"].value == 0.1 for s in log.samples)
        output = destination / f"epochs-{epochs}.eval"
        shutil.copyfile(log.location, output)
        records.append(
            {
                "file": output.name,
                "epochs": epochs,
                "samples": len(log.samples),
                "all_raw_grades": 0.1,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "native_results": [s.model_dump(mode="json") for s in log.results.scores],
            }
        )
    # Raw log directories are redundant with the retained native copies.
    shutil.rmtree(destination / "raw")
    receipt = {
        "inspect_ai": importlib.metadata.version("inspect-ai"),
        "synthetic": True,
        "model": "built-in mockllm; no model API or external grader",
        "runs": records,
    }
    (destination / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Captured {len(records)} native Inspect logs, 80 constant-grade observations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    capture(parser.parse_args().destination)
