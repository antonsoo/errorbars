"""Capture a changed grading rule through lm-eval's built-in exact_match metric.

Constructed local questions and scripted answers, not trained-model performance.
The strict/folded pair keeps every document, target and model answer identical.
Only the recorded ignore_case scorer parameter changes. No network is needed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import re
from pathlib import Path

from datasets import Dataset, DatasetDict
from lm_eval.api.task import ConfigurableTask
from lm_eval.evaluator import evaluate
from lm_eval.loggers import EvaluationTracker
from lm_eval.models.dummy import DummyLM


def dataset(**_: object) -> DatasetDict:
    return DatasetDict({"test": Dataset.from_list([
        {"prompt": f"Controlled grading case {index}: give the requested answer.",
         "target": ["lol", "LOL", "different"][index % 3]}
        for index in range(24)
    ])})


class ImprovedDummyLM(DummyLM):
    def generate_until(self, requests: list) -> list[str]:
        answers = []
        for request in requests:
            match = re.search(r"Controlled grading case (\d+):", request.args[0])
            assert match is not None
            answers.append("LOL" if int(match[1]) % 3 == 1 else "lol")
        return answers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    version = importlib.metadata.version("lm_eval")
    if version != "0.4.13":
        raise RuntimeError(f"Expected lm-eval 0.4.13, found {version}")
    for label in ("strict", "folded", "strict-repeat", "improved-strict", "prompt-variant"):
        declaration = {
            "metric": "exact_match", "aggregation": "mean", "higher_is_better": True,
            "ignore_case": label == "folded", "ignore_punctuation": False,
            "ignore_numbers": False, "regexes_to_ignore": [],
        }
        if label == "strict-repeat":
            declaration = dict(reversed(list(declaration.items())))
        task = ConfigurableTask(config={
            "task": "grading_contract", "custom_dataset": dataset, "test_split": "test",
            "output_type": "generate_until", "num_fewshot": 0,
            "doc_to_text": "Alternate instruction: {{prompt}}" if label == "prompt-variant" else "prompt",
            "doc_to_target": "target", "metric_list": [declaration],
            "generation_kwargs": {"until": ["\n"], "max_gen_toks": 4},
        })
        task.set_fewshot_seed(0)
        model = ImprovedDummyLM() if label == "improved-strict" else DummyLM()
        result = evaluate(model, {"grading_contract": task}, bootstrap_iters=0, log_samples=True)
        assert result is not None
        samples = result.pop("samples")
        result["lm_eval_version"] = version
        tracker = EvaluationTracker(output_path=str(args.out / label))
        tracker.general_config_tracker.log_experiment_args(
            model_source="dummy", model_args=f"model={label}", system_instruction=None,
            chat_template=None, fewshot_as_multiturn=False,
        )
        tracker.save_results_aggregated(result, samples)
        tracker.save_results_samples("grading_contract", samples["grading_contract"])
        print(label, result["results"]["grading_contract"])


if __name__ == "__main__":
    main()
