"""Writes the two small Inspect logs the adapter tests read, through Inspect's built-in
mockllm provider (no network): one task run for two epochs, and one whose scorer returns
named values instead of a single score.

    uv run python tests/fixtures/make_inspect_logs.py <log dir>
"""

import sys

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, match, mean, scorer
from inspect_ai.solver import TaskState, generate

samples = [Sample(id=f"q{i}", input=f"What is {i} + {i}?", target=str(2 * i)) for i in range(1, 4)]


@scorer(metrics={"length": [mean()], "has_digit": [mean()]})
def shape():
    async def score(state: TaskState, target: Target) -> Score:
        text = state.output.completion
        return Score(value={"length": len(text), "has_digit": any(c.isdigit() for c in text)})

    return score


def run(task: Task, **options: object) -> None:
    log = eval(task, model="mockllm/model", log_dir=sys.argv[1], display="none", **options)[0]
    print(log.location, log.status)


run(Task(dataset=samples, solver=generate(), scorer=match(), name="tiny_epochs"), epochs=2)
run(Task(dataset=samples, solver=generate(), scorer=shape(), name="tiny_named_values"))
