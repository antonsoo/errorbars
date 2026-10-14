"""A smaller valid JSONL file is not necessarily the recorded evaluated cohort."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from errorbars.adapters.lm_eval import load_lm_eval_samples, model_metadata_path
from errorbars.inputs import load_inputs
from errorbars.io import write_csv

FIXTURES = Path(__file__).parent / "fixtures"
TINY = next((FIXTURES / "lm_eval_output/sshleifer__tiny-gpt2").glob("samples_*.jsonl"))
MULTIFILTER = next(FIXTURES.glob("samples_gsm8k_*.jsonl"))


def copy_native(folder: Path) -> tuple[Path, Path]:
    samples = folder / TINY.name
    shutil.copyfile(TINY, samples)
    metadata = model_metadata_path(samples)
    assert metadata is not None
    shutil.copyfile(next(TINY.parent.glob("results_*.json")), metadata)
    return samples, metadata


@pytest.mark.parametrize("name", [None, "explicit-name"])
def test_removed_incorrect_answers_do_not_become_a_perfect_evaluation(tmp_path: Path, name: str | None):
    samples, metadata = copy_native(tmp_path)
    original = metadata.read_bytes()
    rows = [line for line in samples.read_text().splitlines() if json.loads(line)["acc"] == 1]
    assert len(rows) == 12
    samples.write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match=r"cohort mismatch.*12 selected samples.*20 evaluated"):
        load_lm_eval_samples(samples, model=name)
    assert metadata.read_bytes() == original


def test_a_limited_native_run_uses_effective_not_original_count(tmp_path: Path):
    samples, metadata = copy_native(tmp_path)
    declared = json.loads(metadata.read_text())["n-samples"]["copa"]
    assert declared == {"original": 100, "effective": 20}
    data = load_lm_eval_samples(samples)
    assert len(data) == 20 and sum(data.score) / len(data) == 0.6


def test_count_is_per_selected_filter_not_total_records(tmp_path: Path):
    samples = tmp_path / MULTIFILTER.name
    shutil.copyfile(MULTIFILTER, samples)
    metadata = model_metadata_path(samples)
    assert metadata is not None
    metadata.write_text(json.dumps({"n-samples": {"gsm8k_cot_self_consistency": {"effective": 4}}}))
    rows = samples.read_text().splitlines()
    assert len(rows) == 12
    assert len(load_lm_eval_samples(samples, model="m", filter_name="maj@8")) == 4
    removed = next(line for line in rows if json.loads(line)["filter"] == "maj@8")
    samples.write_text("\n".join(line for line in rows if line != removed) + "\n")
    assert len(load_lm_eval_samples(samples, model="m", filter_name="score-first")) == 4
    with pytest.raises(ValueError, match=r"filter 'maj@8'.*3 selected samples.*4 evaluated"):
        load_lm_eval_samples(samples, model="m", filter_name="maj@8")


@pytest.mark.parametrize("value", [True, False, 20.0, "20", None, 0, -1, [], {}])
def test_malformed_declared_count_cannot_be_bypassed_by_naming_the_model(tmp_path: Path, value: object):
    samples, metadata = copy_native(tmp_path)
    metadata.write_text(json.dumps({"n-samples": {"copa": {"effective": value}}}))
    with pytest.raises(ValueError, match="'effective' must be a positive integer"):
        load_lm_eval_samples(samples, model="explicit")


@pytest.mark.parametrize("body", ["[]", "{", '{"n-samples":null}', '{"n-samples":{"copa":null}}',
                                  '{"model_name":"m","model_name":"other"}'])
def test_damaged_matching_results_are_rejected_even_with_an_explicit_name(tmp_path: Path, body: str):
    samples, metadata = copy_native(tmp_path)
    metadata.write_text(body)
    with pytest.raises(ValueError):
        load_lm_eval_samples(samples, model="explicit")


@pytest.mark.parametrize("body", [{}, {"n-samples": {}}, {"n-samples": {"copa": {"original": 100}}}])
def test_missing_count_evidence_stays_usable_without_inventing_a_count(tmp_path: Path, body: dict):
    samples, metadata = copy_native(tmp_path)
    metadata.write_text(json.dumps(body))
    assert len(load_lm_eval_samples(samples, model="explicit")) == 20


def test_orphan_samples_do_not_use_an_unrelated_results_count(tmp_path: Path):
    samples = tmp_path / TINY.name
    shutil.copyfile(TINY, samples)
    (tmp_path / "results_2026-01-01T00-00-00.000000.json").write_text(
        '{"n-samples":{"copa":{"effective":999}}}'
    )
    assert len(load_lm_eval_samples(samples, model="explicit")) == 20


@pytest.mark.parametrize("n", [19, 21])
def test_more_or_fewer_unique_samples_conflict_with_the_recorded_count(tmp_path: Path, n: int):
    samples, _metadata = copy_native(tmp_path)
    rows = samples.read_text().splitlines()
    if n == 19:
        rows.pop()
    else:
        rows.append(json.dumps({**json.loads(rows[-1]), "doc_id": 999}))
    samples.write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match=f"{n} selected samples.*20 evaluated"):
        load_lm_eval_samples(samples, model="explicit")


@pytest.mark.parametrize("named", [False, True])
@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink"])
def test_import_preserves_count_sidecar_with_inferred_and_explicit_models(
    tmp_path: Path, named: bool, alias: str,
):
    samples, metadata = copy_native(tmp_path)
    original = metadata.read_bytes()
    loaded = load_inputs([f"explicit={samples}" if named else samples])
    assert metadata in loaded.protected_paths
    output = tmp_path / "export.csv"
    if alias == "same":
        output = metadata
    elif alias == "hardlink":
        output.hardlink_to(metadata)
    else:
        output.symlink_to(metadata.name)
    with pytest.raises(ValueError, match="output must not"):
        write_csv(loaded.data, output, protected=loaded.protected_paths)
    assert metadata.read_bytes() == original
