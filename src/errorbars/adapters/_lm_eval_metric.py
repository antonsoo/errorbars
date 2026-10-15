"""Read the selected metric's declarations without executing harness code.

Scalar samples can be inputs to a corpus aggregation rather than scores in that
metric's units. In particular, lm-eval's perplexity samples are log likelihoods.
Errorbars estimates arithmetic question means; it cannot infer arbitrary
aggregation functions or apply their aggregate direction to their raw inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from errorbars.scoring import ScoringRule


def metric_scoring_rule(
    results: dict[str, object] | None, task: str | None, metric: str, path: Path,
) -> ScoringRule:
    """Fingerprint recorded kwargs actually used by default generation scoring.

    ``metric_direction`` validates the container shapes before this is called.
    Custom process_results overrides metric kwargs; other output types use
    separate scoring branches. Neither can be certified by hashing unused kwargs.
    Matching declarations do not establish matching registered metric code.
    """
    name = "lm-eval:" + metric
    configs = results.get("configs") if results is not None else None
    config = configs.get(task) if isinstance(configs, dict) else None
    if not isinstance(config, dict) or config.get("output_type") != "generate_until":
        return ScoringRule(name)
    if config.get("process_results") is not None:
        return ScoringRule(name)
    declarations = config.get("metric_list")
    if not isinstance(declarations, list):
        return ScoringRule(name)
    fingerprints = set()
    for declaration in declarations:
        if not isinstance(declaration, dict) or declaration.get("metric") != metric:
            continue
        backend = declaration.get("hf_evaluate", False)
        if type(backend) is not bool:
            raise ValueError(f"{path}: metric {metric!r}: hf_evaluate must be a boolean")
        # task.py forwards all remaining fields to the generation metric. Mean
        # aggregation and display direction do not change these per-item grades.
        parameters = {key: value for key, value in declaration.items()
                      if key not in {"metric", "aggregation", "higher_is_better", "hf_evaluate"}}
        try:
            canonical = json.dumps(
                {"parameters": parameters, "hf_evaluate": backend}, sort_keys=True,
                ensure_ascii=True, separators=(",", ":"), allow_nan=False,
            )
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(f"{path}: metric {metric!r}: invalid recorded grading parameters") from exc
        fingerprints.add(
            "lm-eval-generation-params-v1:" + hashlib.sha256(canonical.encode("ascii")).hexdigest()
        )
    if len(fingerprints) > 1:
        raise ValueError(f"{path}: metric {metric!r}: conflicting recorded grading parameters")
    return ScoringRule(name, next(iter(fingerprints), None))


def metric_direction(
    results: dict[str, object] | None, task: str | None, metric: str, path: Path,
) -> bool | None:
    """Validate available metric evidence and return its recorded direction.

    Missing metadata remains unknown; a metric name does not identify its
    implementation or aggregation. A recorded lower-is-better direction needs
    a recorded mean aggregation: applying an aggregate's direction to arbitrary
    scalar inputs can reverse the ordering.
    """
    directions: set[bool] = set()
    aggregations: set[str] = set()

    def direction(value: object) -> None:
        if value is None:
            return
        if type(value) is not bool:
            raise ValueError(f"{path}: metric {metric!r}: higher_is_better must be a boolean or null")
        directions.add(value)

    if results is not None:
        if "higher_is_better" in results:
            mapping = results["higher_is_better"]
            if not isinstance(mapping, dict):
                raise ValueError(f"{path}: invalid higher_is_better; expected per-task metric directions")
            if task in mapping:
                task_directions = mapping[task]
                if not isinstance(task_directions, dict):
                    raise ValueError(f"{path}: invalid higher_is_better for task {task!r}")
                if metric in task_directions:
                    direction(task_directions[metric])
        if "configs" in results:
            configs = results["configs"]
            if not isinstance(configs, dict):
                raise ValueError(f"{path}: invalid configs; expected per-task configurations")
            if task in configs:
                config = configs[task]
                if not isinstance(config, dict):
                    raise ValueError(f"{path}: invalid configuration for task {task!r}")
                if "metric_list" in config:
                    declarations = config["metric_list"]
                    if not isinstance(declarations, list):
                        raise ValueError(f"{path}: task {task!r}: metric_list must be a list")
                    for declaration in declarations:
                        if not isinstance(declaration, dict):
                            raise ValueError(f"{path}: task {task!r}: metric_list entries must be objects")
                        if declaration.get("metric") != metric:
                            continue
                        direction(declaration.get("higher_is_better"))
                        aggregation = declaration.get("aggregation")
                        if aggregation is not None:
                            if not isinstance(aggregation, str) or not aggregation.strip():
                                raise ValueError(
                                    f"{path}: metric {metric!r}: aggregation must be a nonempty string"
                                )
                            aggregations.add(aggregation)
    if len(directions) > 1:
        raise ValueError(f"{path}: metric {metric!r}: conflicting higher_is_better declarations")
    if len(aggregations) > 1:
        raise ValueError(f"{path}: metric {metric!r}: conflicting aggregation declarations")
    aggregation = next(iter(aggregations), None)
    # Scores are already finite, so the harness's nanmean equals its mean.
    if aggregation is not None and aggregation not in ("mean", "nanmean"):
        label = aggregation
        label = repr(label) if re.fullmatch(r"[\w+.-]{1,60}", label) else "a custom function"
        raise ValueError(
            f"{path}: metric {metric!r} uses aggregation {label}, not an arithmetic mean. "
            "Its per-item values cannot be treated as scores in that metric's units. "
            "Select a metric with aggregation='mean', or compute and document appropriate "
            "per-question scores before importing them as CSV/JSONL."
        )
    selected = next(iter(directions), None)
    if selected is False and aggregation is None:
        raise ValueError(
            f"{path}: lower-is-better metric {metric!r} has no recorded mean aggregation. "
            "The aggregate's direction cannot safely order its per-item inputs; "
            "restore the matching results configuration or supply documented per-question scores."
        )
    return selected
