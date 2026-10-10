"""Record a controlled score-order experiment through lm-eval 0.4.13 itself.

No downloaded dataset, model weights, API calls, or trained-model quality claims.
The real DummyLM returns 'lol'. Exact and case-insensitive scorers judge it
against 'LOL'; the two runs differ only in the scorer dictionary's insertion order.
"""

from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path

from datasets import Dataset, DatasetDict
from lm_eval.api.task import ConfigurableTask
from lm_eval.evaluator import evaluate
from lm_eval.loggers import EvaluationTracker
from lm_eval.models.dummy import DummyLM


def dataset(**_: object) -> DatasetDict:
    return DatasetDict(
        {
            "test": Dataset.from_list(
                [{"prompt": f"Controlled case {i}: reply with LOL.", "target": "LOL"} for i in range(24)]
            )
        }
    )


def exact_first(doc: dict, results: list[str]) -> dict[str, int]:
    return {
        "exact": int(results[0] == doc["target"]),
        "casefold": int(results[0].casefold() == doc["target"].casefold()),
    }


def casefold_first(doc: dict, results: list[str]) -> dict[str, int]:
    return dict(reversed(list(exact_first(doc, results).items())))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    version = importlib.metadata.version("lm_eval")
    if version != "0.4.13":
        raise RuntimeError(f"Expected lm-eval 0.4.13, found {version}")
    for label, scorer in [("exact-first", exact_first), ("casefold-first", casefold_first)]:
        task = ConfigurableTask(
            config={
                "task": "case_control",
                "custom_dataset": dataset,
                "test_split": "test",
                "output_type": "generate_until",
                "doc_to_text": "prompt",
                "doc_to_target": "target",
                "num_fewshot": 0,
                "process_results": scorer,
                "generation_kwargs": {"until": ["\n"], "max_gen_toks": 4},
                "metric_list": [
                    {"metric": name, "aggregation": "mean", "higher_is_better": True}
                    for name in ("exact", "casefold")
                ],
            }
        )
        task.set_fewshot_seed(0)
        result = evaluate(DummyLM(), {"case_control": task}, bootstrap_iters=0, log_samples=True)
        assert result is not None
        samples = result.pop("samples")
        result["lm_eval_version"] = version
        tracker = EvaluationTracker(output_path=str(args.out / label))
        tracker.general_config_tracker.log_experiment_args(
            model_source="dummy",
            model_args="model=controlled-dummy",
            system_instruction=None,
            chat_template=None,
            fewshot_as_multiturn=False,
        )
        tracker.save_results_aggregated(result, samples)
        tracker.save_results_samples("case_control", samples["case_control"])
        print(label, result["results"]["case_control"])


if __name__ == "__main__":
    main()
