"""Adapter tests, against real (not hand-written) fixture logs.

tests/fixtures/samples_copa_*.jsonl and samples_arc_easy_*.jsonl are
unedited `--log_samples` output from lm-eval 0.4.13 (`lm_eval run --model
dummy --tasks copa --limit 20 --log_samples ...` / `--tasks arc_easy
--limit 5`); samples_gsm8k_cot_self_consistency_*.jsonl is the same for a
task with three filters (`--limit 4`). tests/fixtures/inspect_tiny_qa.eval is
an unedited log from inspect-ai 0.3.268 running a 5-sample task through
`mockllm/model`; inspect_tiny_epochs.eval and inspect_tiny_named_values.eval
are written by tests/fixtures/make_inspect_logs.py the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from errorbars.adapters.lm_eval import load_lm_eval_samples

FIXTURES = Path(__file__).parent / "fixtures"
COPA = FIXTURES / "samples_copa_2026-09-24T03-04-37.941131.jsonl"
ARC_EASY = FIXTURES / "samples_arc_easy_2026-09-24T03-05-32.831346.jsonl"
GSM8K_FILTERS = FIXTURES / "samples_gsm8k_cot_self_consistency_2026-10-01T13-21-10.261566.jsonl"
INSPECT_LOG = FIXTURES / "inspect_tiny_qa.eval"
INSPECT_EPOCHS = FIXTURES / "inspect_tiny_epochs.eval"
INSPECT_NAMED_VALUES = FIXTURES / "inspect_tiny_named_values.eval"


class TestLmEvalAdapter:
    def test_loads_single_metric_task(self) -> None:
        data = load_lm_eval_samples(COPA, model="dummy-copa")
        assert len(data) == 20
        assert data.models() == ["dummy-copa"]
        assert data.question_id[:3] == ["copa-0", "copa-1", "copa-2"]
        assert all(s in (0.0, 1.0) for s in data.score)

    def test_task_name_inferred_from_filename_prefixes_question_id(self) -> None:
        data = load_lm_eval_samples(COPA, model="m")
        assert all(qid.startswith("copa-") for qid in data.question_id)

    def test_multi_metric_task_defaults_to_first_metric(self) -> None:
        data = load_lm_eval_samples(ARC_EASY, model="m")
        # First metric in each arc_easy record's "metrics" list is "acc".
        default_scores = data.score
        explicit = load_lm_eval_samples(ARC_EASY, model="m", metric="acc")
        assert default_scores == explicit.score

    def test_multi_metric_task_explicit_metric_selection(self) -> None:
        acc = load_lm_eval_samples(ARC_EASY, model="m", metric="acc")
        acc_norm = load_lm_eval_samples(ARC_EASY, model="m", metric="acc_norm")
        assert len(acc) == len(acc_norm) == 5
        # Not asserting they differ (they needn't, for a dummy model) but both
        # must be valid 0/1 scores pulled from distinct top-level keys.
        assert all(s in (0.0, 1.0) for s in acc_norm.score)

    def test_unknown_metric_raises(self) -> None:
        with pytest.raises(ValueError, match="not present"):
            load_lm_eval_samples(COPA, model="m", metric="does_not_exist")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_lm_eval_samples(tmp_path / "nope.jsonl", model="m")

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "samples_empty_2026-01-01T00-00-00.000000.jsonl"
        p.write_text("")
        with pytest.raises(ValueError, match="no records"):
            load_lm_eval_samples(p, model="m")

    def test_record_without_metrics_list_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "samples_bad_2026-01-01T00-00-00.000000.jsonl"
        p.write_text('{"doc_id": 0}\n')
        with pytest.raises(ValueError, match="metrics"):
            load_lm_eval_samples(p, model="m")

    def test_a_task_with_several_filters_needs_one_chosen(self) -> None:
        # 4 questions scored under 3 filters: 12 records. Read as 12 questions they would
        # triple n and shrink every standard error.
        with pytest.raises(ValueError, match=r"3 filters \(score-first, maj@64, maj@8\)"):
            load_lm_eval_samples(GSM8K_FILTERS, model="dummy")

    def test_one_filter_gives_each_question_once(self) -> None:
        data = load_lm_eval_samples(GSM8K_FILTERS, model="dummy", filter_name="maj@8")
        assert data.question_id == [f"gsm8k_cot_self_consistency-{i}" for i in range(4)]

    def test_unknown_filter_lists_the_ones_in_the_file(self) -> None:
        with pytest.raises(ValueError, match=r"no records for filter 'maj@3' \(has: score-first"):
            load_lm_eval_samples(GSM8K_FILTERS, model="dummy", filter_name="maj@3")

    def test_single_filter_file_needs_no_choice(self) -> None:
        assert len(load_lm_eval_samples(COPA, model="m", filter_name="none")) == 20

    def test_repeated_doc_id_is_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "samples_dup_2026-01-01T00-00-00.000000.jsonl"
        record = '{"doc_id": 7, "metrics": ["acc"], "acc": 1.0}\n'
        p.write_text(record * 2)
        with pytest.raises(ValueError, match=r":2: a second record for doc_id 7 \(first on line 1\)"):
            load_lm_eval_samples(p, model="m")

    @pytest.mark.parametrize("value", ["NaN", "Infinity", '"n/a"', "null", "[1]"])
    def test_metric_that_is_not_a_finite_number_is_rejected(self, tmp_path: Path, value: str) -> None:
        p = tmp_path / "samples_bad_2026-01-01T00-00-00.000000.jsonl"
        p.write_text(f'{{"doc_id": 0, "metrics": ["acc"], "acc": {value}}}\n')
        with pytest.raises(ValueError, match="metric 'acc', line 1"):
            load_lm_eval_samples(p, model="m")

    @pytest.mark.parametrize("line", ["[]", "3", "null", '{"doc_id": 0, "metrics": "acc", "acc": 1}'])
    def test_record_of_the_wrong_shape_is_rejected(self, tmp_path: Path, line: str) -> None:
        p = tmp_path / "samples_bad_2026-01-01T00-00-00.000000.jsonl"
        p.write_text(line + "\n")
        with pytest.raises(ValueError, match=":1: "):
            load_lm_eval_samples(p, model="m")


class TestInspectAdapter:
    def test_loads_tiny_qa_log(self) -> None:
        inspect_ai = pytest.importorskip("inspect_ai")
        del inspect_ai
        from errorbars.adapters.inspect_ai import load_inspect_log

        data = load_inspect_log(INSPECT_LOG)
        assert len(data) == 5
        assert data.models() == ["mockllm/model"]
        assert data.question_id == ["1", "2", "3", "4", "5"]
        assert data.sample == ["1", "1", "1", "1", "1"]  # single epoch
        assert all(s in (0.0, 1.0, 0.5) for s in data.score)

    def test_explicit_scorer_matches_default_when_only_one(self) -> None:
        pytest.importorskip("inspect_ai")
        from errorbars.adapters.inspect_ai import load_inspect_log

        default = load_inspect_log(INSPECT_LOG)
        explicit = load_inspect_log(INSPECT_LOG, scorer="match")
        assert default.score == explicit.score

    def test_unknown_scorer_raises(self) -> None:
        pytest.importorskip("inspect_ai")
        from errorbars.adapters.inspect_ai import load_inspect_log

        with pytest.raises(ValueError, match="no scorer"):
            load_inspect_log(INSPECT_LOG, scorer="does_not_exist")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        pytest.importorskip("inspect_ai")
        from errorbars.adapters.inspect_ai import load_inspect_log

        with pytest.raises(Exception):  # noqa: B017 - Inspect raises its own FileNotFoundError subclass
            load_inspect_log(tmp_path / "nope.eval")

    def test_epochs_become_the_sample_column(self) -> None:
        pytest.importorskip("inspect_ai")
        from errorbars.adapters.inspect_ai import load_inspect_log

        data = load_inspect_log(INSPECT_EPOCHS)
        assert data.question_id == ["q1", "q2", "q3", "q1", "q2", "q3"]
        assert data.sample == ["1", "1", "1", "2", "2", "2"]

    def test_scorer_with_named_values_is_rejected(self) -> None:
        # Inspect's own conversion reads a dict of values as 0.0, so every sample scored 0.
        pytest.importorskip("inspect_ai")
        from errorbars.adapters.inspect_ai import load_inspect_log

        with pytest.raises(ValueError, match="scorer 'shape' returns dict values"):
            load_inspect_log(INSPECT_NAMED_VALUES)

    def test_file_that_is_not_a_log_is_named(self, tmp_path: Path) -> None:
        pytest.importorskip("inspect_ai")
        from errorbars.adapters.inspect_ai import load_inspect_log

        p = tmp_path / "notes.eval"
        p.write_text("not a log")
        with pytest.raises(ValueError, match=r"notes\.eval: not a log Inspect can read"):
            load_inspect_log(p)

