"""Score selection must not depend on metadata order or another run's identity."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from errorbars.adapters.lm_eval import infer_model_name, load_lm_eval_samples
from errorbars.inputs import load_inputs

FIXTURES = Path(__file__).parent / "fixtures"
ARC = next(FIXTURES.glob("samples_arc_easy_*.jsonl"))
TINY = next((FIXTURES / "lm_eval_output" / "sshleifer__tiny-gpt2").glob("samples_*.jsonl"))
RANDOM = next((FIXTURES / "lm_eval_output" / "hf-internal-testing__tiny-random-gpt2").glob("results_*.json"))


def write_records(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    return path


def arc_records() -> list[dict]:
    return [json.loads(line) for line in ARC.read_text().splitlines()]


@pytest.mark.parametrize("metric", ["doc_id", "target", "missing", ""])
def test_only_declared_metrics_can_be_selected(metric: str) -> None:
    with pytest.raises(ValueError, match="not declared"):
        load_lm_eval_samples(ARC, model="m", metric=metric)


@pytest.mark.parametrize("metrics", [["acc", "acc"], ["acc", None], [3], [""]])
def test_malformed_metric_names_fail_with_source_line(tmp_path: Path, metrics: list) -> None:
    records = arc_records()
    records[2]["metrics"] = metrics
    path = write_records(tmp_path / ARC.name, records)
    with pytest.raises(ValueError, match=r":3:.*metrics"):
        load_lm_eval_samples(path, model="m", metric="acc")


def test_explicit_selection_survives_arbitrary_metric_order(tmp_path: Path) -> None:
    records = arc_records()
    for row in records[::2]:
        row["metrics"].reverse()
    path = write_records(tmp_path / ARC.name, records)
    for metric in ("acc", "acc_norm"):
        expected = [row[metric] for row in records]
        loaded = load_lm_eval_samples(path, model="m", metric=metric)
        assert loaded.score == expected
        assert all(source.metric == metric for source in loaded.sources if source)
    with pytest.raises(ValueError, match="multiple metrics"):
        load_lm_eval_samples(path, model="m")


def test_inferred_metric_cannot_switch_mid_file(tmp_path: Path) -> None:
    records = arc_records()
    for row in records:
        row["metrics"] = ["acc"]
    records[3]["metrics"] = ["acc_norm"]
    path = write_records(tmp_path / ARC.name, records)
    with pytest.raises(ValueError, match=r":4: metric 'acc' is not declared"):
        load_lm_eval_samples(path, model="m")


def test_declared_but_absent_score_is_not_replaced(tmp_path: Path) -> None:
    records = arc_records()
    del records[1]["acc"]
    path = write_records(tmp_path / ARC.name, records)
    with pytest.raises(ValueError, match=r":2: metric 'acc' not present"):
        load_lm_eval_samples(path, model="m", metric="acc")


def test_only_selected_filter_determines_metric_ambiguity(tmp_path: Path) -> None:
    records = arc_records()
    for row in records:
        row["filter"] = "selected"
        row["metrics"] = ["acc"]
    unused = {**records[0], "filter": "unused", "metrics": ["acc", "acc_norm"]}
    path = write_records(tmp_path / ARC.name, [unused, *records])
    result = load_lm_eval_samples(path, model="m", filter_name="selected")
    assert result.score == [row["acc"] for row in records]
    assert result.sources[0].line_start == 2


@pytest.mark.parametrize("renamed", [False, True])
def test_other_run_cannot_supply_the_model_name(tmp_path: Path, renamed: bool) -> None:
    samples = tmp_path / ("renamed.jsonl" if renamed else TINY.name)
    shutil.copyfile(TINY, samples)
    shutil.copyfile(RANDOM, tmp_path / RANDOM.name)
    assert infer_model_name(samples) is None
    with pytest.raises(ValueError, match="matching-timestamp"):
        load_inputs([samples])
    assert load_inputs([f"explicit={samples}"]).data.models() == ["explicit"]


def test_matching_metadata_is_used_among_unrelated_results(tmp_path: Path) -> None:
    samples = tmp_path / TINY.name
    shutil.copyfile(TINY, samples)
    shutil.copyfile(RANDOM, tmp_path / RANDOM.name)
    matching = next(TINY.parent.glob("results_*.json"))
    shutil.copyfile(matching, tmp_path / matching.name)
    assert infer_model_name(samples) == "sshleifer/tiny-gpt2"


def test_shared_questions_require_the_same_metric_across_native_logs(tmp_path: Path) -> None:
    paths = []
    for metric in ("acc", "acc_norm"):
        records = arc_records()
        for row in records:
            row["metrics"] = [metric]
        paths.append(f"{metric}={write_records(tmp_path / metric / ARC.name, records)}")
    with pytest.raises(ValueError, match="question 'arc_easy-0' uses metric 'acc_norm'"):
        load_inputs(paths)
    # Disjoint tasks may still use their own score names in a user-chosen benchmark.
    other = tmp_path / "samples_other_2026-09-24T03-05-32.831346.jsonl"
    write_records(other, records)
    assert len(load_inputs([paths[0], f"acc_norm={other}"]).data) == 10
