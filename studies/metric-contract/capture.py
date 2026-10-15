"""Capture scalar metric semantics through lm-eval 0.4.13 itself.

The dataset and model log likelihoods are constructed, not measurements of a
trained model. Both runs use the same documents, targets and scoring function.
The harness writes its native samples and matching results without editing.
No model weights, external dataset or API service are used.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import math
import re
from pathlib import Path

from datasets import Dataset, DatasetDict
from lm_eval.api.task import ConfigurableTask
from lm_eval.evaluator import evaluate
from lm_eval.loggers import EvaluationTracker
from lm_eval.models.dummy import DummyLM


def dataset(**_: object) -> DatasetDict:
    return DatasetDict({"test": Dataset.from_list([
        {"prompt": f"Controlled metric case {i}:", "target": " correct"} for i in range(32)
    ])})


def metrics(doc: dict, results: list[tuple[float, bool]]) -> dict[str, float]:
    log_probability = results[0][0]
    return {
        "mean_nll": -log_probability,
        "likelihood": math.exp(log_probability),
        "perplexity": log_probability,
    }


class ScriptedLikelihoods(DummyLM):
    def __init__(self, precise: bool):
        super().__init__()
        self.precise = precise

    def loglikelihood(self, requests: list) -> list[tuple[float, bool]]:
        outcomes = []
        for request in requests:
            match = re.search(r"Controlled metric case (\d+):", request.args[0])
            assert match is not None
            index = int(match[1])
            nll = (index % 4 + 1) / 10 if self.precise else (index % 5 + 6) / 10
            outcomes.append((-nll, False))
        return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    version = importlib.metadata.version("lm_eval")
    if version != "0.4.13":
        raise RuntimeError(f"Expected lm-eval 0.4.13, found {version}")
    for label in ("precise", "noisy"):
        task = ConfigurableTask(config={
            "task": "metric_contract",
            "custom_dataset": dataset,
            "test_split": "test",
            "output_type": "loglikelihood",
            "doc_to_text": "prompt",
            "doc_to_target": "target",
            "num_fewshot": 0,
            "process_results": metrics,
            "metric_list": [
                {"metric": "mean_nll", "aggregation": "mean", "higher_is_better": False},
                {"metric": "likelihood", "aggregation": "mean", "higher_is_better": True},
                {"metric": "perplexity", "aggregation": "perplexity", "higher_is_better": False},
            ],
        })
        task.set_fewshot_seed(0)
        result = evaluate(
            ScriptedLikelihoods(label == "precise"), {"metric_contract": task},
            bootstrap_iters=0, log_samples=True,
        )
        assert result is not None
        samples = result.pop("samples")
        result["lm_eval_version"] = version
        tracker = EvaluationTracker(output_path=str(args.out / label))
        tracker.general_config_tracker.log_experiment_args(
            model_source="scripted", model_args=f"model={label}",
            system_instruction=None, chat_template=None, fewshot_as_multiturn=False,
        )
        tracker.save_results_aggregated(result, samples)
        tracker.save_results_samples("metric_contract", samples["metric_contract"])
        print(label, result["results"]["metric_contract"])


if __name__ == "__main__":
    main()
