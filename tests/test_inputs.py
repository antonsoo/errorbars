"""Several inputs, as harnesses leave them.

tests/fixtures/lm_eval_output/ is the output directory of two real lm-eval 0.4.13 runs
(`lm_eval run --model hf --model_args pretrained=<model> --device cpu --tasks copa --limit 20
--log_samples --output_path lm_eval_output`, for sshleifer/tiny-gpt2 and
hf-internal-testing/tiny-random-gpt2). The samples files are unedited. The results files are
cut down to a handful of keys: the originals also carry a dump of the machine they ran on
and a local path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from errorbars.adapters.lm_eval import infer_model_name, load_lm_eval_samples
from errorbars.inputs import load_inputs, split_spec
from errorbars.io import EvalData, concat

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
OUTPUT = FIXTURES / "lm_eval_output"
TINY = OUTPUT / "sshleifer__tiny-gpt2"
RANDOM = OUTPUT / "hf-internal-testing__tiny-random-gpt2"
TINY_SAMPLES = TINY / "samples_copa_2026-10-01T23-15-32.942677.jsonl"
RANDOM_SAMPLES = RANDOM / "samples_copa_2026-10-01T23-15-52.736695.jsonl"
DUMMY_COPA = FIXTURES / "samples_copa_2026-09-24T03-04-37.941131.jsonl"
INSPECT_LOG = FIXTURES / "inspect_tiny_qa.eval"
DATA = REPO_ROOT / "examples" / "data" / "reading_comprehension.csv"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "errorbars.cli", *args], capture_output=True, text=True, cwd=REPO_ROOT
    )


def harness_accuracy(model_dir: Path) -> float:
    """The accuracy lm-eval itself reported for the run in `model_dir`."""
    (results,) = model_dir.glob("results_*.json")
    return float(json.loads(results.read_text())["results"]["copa"]["acc,none"])


class TestLmEvalOutputDirectory:
    def test_the_model_is_read_from_the_results_file_beside_the_samples(self) -> None:
        assert infer_model_name(TINY_SAMPLES) == "sshleifer/tiny-gpt2"
        assert infer_model_name(RANDOM_SAMPLES) == "hf-internal-testing/tiny-random-gpt2"
        data = load_lm_eval_samples(TINY_SAMPLES)
        assert data.models() == ["sshleifer/tiny-gpt2"]

    def test_two_model_directories_are_one_dataset(self) -> None:
        loaded = load_inputs([TINY, RANDOM])
        assert loaded.data.models() == ["sshleifer/tiny-gpt2", "hf-internal-testing/tiny-random-gpt2"]
        assert len(loaded.data) == 40
        assert loaded.files == [TINY_SAMPLES, RANDOM_SAMPLES]
        assert loaded.notes == []
        # Same task, same documents: the questions pair up.
        by_model = {m: set(loaded.data.filter_model(m).question_id) for m in loaded.data.models()}
        assert by_model["sshleifer/tiny-gpt2"] == by_model["hf-internal-testing/tiny-random-gpt2"]

    def test_compare_takes_the_two_directories_and_agrees_with_the_harness(self) -> None:
        result = run_cli("compare", str(TINY), str(RANDOM), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["model_a"] == "sshleifer/tiny-gpt2"
        assert payload["model_b"] == "hf-internal-testing/tiny-random-gpt2"
        assert payload["n"] == 20
        assert payload["n_only_a"] == payload["n_only_b"] == 0
        # The means are the accuracies lm-eval printed for these runs (0.6 and 0.8).
        assert payload["mean_a"] == pytest.approx(harness_accuracy(TINY))
        assert payload["mean_b"] == pytest.approx(harness_accuracy(RANDOM))
        assert payload["mean_diff"] == pytest.approx(-0.2)

    def test_the_output_root_is_a_leaderboard(self) -> None:
        result = run_cli("leaderboard", str(OUTPUT), "--json")
        assert result.returncode == 0, result.stderr
        entries = json.loads(result.stdout)["entries"]
        assert [(e["model"], e["n"]) for e in entries] == [
            ("hf-internal-testing/tiny-random-gpt2", 20),
            ("sshleifer/tiny-gpt2", 20),
        ]

    def test_summarize_names_the_model_of_a_single_log(self) -> None:
        result = run_cli("summarize", str(TINY_SAMPLES), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["model"] == "sshleifer/tiny-gpt2"
        assert payload["mean"] == pytest.approx(0.6)
        # lm-eval logs no clusters, and the questions are not clusters of themselves.
        assert "clustered" not in payload

    def test_a_rerun_in_the_same_directory_uses_the_latest_and_says_so(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "sshleifer__tiny-gpt2"
        shutil.copytree(TINY, model_dir)
        # An earlier run of the same task: every answer wrong.
        older = model_dir / "samples_copa_2026-09-30T08-00-00.000000.jsonl"
        lines = [json.loads(line) for line in TINY_SAMPLES.read_text().splitlines()]
        older.write_text("".join(json.dumps({**rec, "acc": 0.0}) + "\n" for rec in lines))
        loaded = load_inputs([model_dir])
        assert [f.name for f in loaded.files] == [TINY_SAMPLES.name]
        assert sum(loaded.data.score) / len(loaded.data) == pytest.approx(0.6)
        assert len(loaded.notes) == 1
        assert "2 runs of copa" in loaded.notes[0] and TINY_SAMPLES.name in loaded.notes[0]

        result = run_cli("summarize", str(model_dir), "--json")
        assert result.returncode == 0, result.stderr
        assert "note: " in result.stderr and "2 runs of copa" in result.stderr
        # The older run is still there to be read when it is the one asked for.
        assert load_inputs([older]).data.score == [0.0] * 20

    def test_a_samples_file_away_from_its_results_file_has_to_be_named(self, tmp_path: Path) -> None:
        moved = tmp_path / TINY_SAMPLES.name
        shutil.copy(TINY_SAMPLES, moved)
        assert infer_model_name(moved) is None
        with pytest.raises(ValueError, match="can't tell which model wrote this"):
            load_inputs([moved])
        named = load_inputs([f"tiny={moved}"])
        assert named.data.models() == ["tiny"]

        result = run_cli("summarize", str(moved))
        assert result.returncode != 0
        assert result.stderr.startswith("error: ") and "NAME=PATH" in result.stderr
        assert "Traceback" not in result.stderr

    def test_an_empty_directory_says_what_it_looked_for(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no lm-eval samples_\\*.jsonl files or Inspect .eval logs"):
            load_inputs([tmp_path])


class TestSeveralFiles:
    def test_the_same_run_twice_is_refused(self) -> None:
        with pytest.raises(ValueError, match="already has a score for question 'copa-0'"):
            load_inputs([TINY, TINY])
        result = run_cli("compare", str(TINY), str(TINY))
        assert result.returncode != 0
        assert "already has a score" in result.stderr and "Traceback" not in result.stderr

    def test_two_runs_of_one_model_are_told_apart_by_name(self) -> None:
        loaded = load_inputs([f"first={TINY_SAMPLES}", f"second={TINY_SAMPLES}"])
        assert loaded.data.models() == ["first", "second"]
        result = run_cli("compare", f"first={TINY_SAMPLES}", f"second={TINY_SAMPLES}", "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["model_a"], payload["model_b"]) == ("first", "second")
        assert payload["mean_diff"] == 0.0

    def test_split_csvs_give_the_leaderboard_of_the_whole(self, tmp_path: Path) -> None:
        # One file per model, the way results arrive, against the single file they came from.
        header, *rows = DATA.read_text().splitlines()
        model_at = header.split(",").index("model")
        models: dict[str, list[str]] = {}
        for row in rows:
            models.setdefault(row.split(",")[model_at], []).append(row)
        paths = []
        for i, (_, model_rows) in enumerate(models.items()):
            path = tmp_path / f"part-{i}.csv"
            path.write_text("\n".join([header, *model_rows]) + "\n")
            paths.append(str(path))
        assert len(paths) == 4
        whole = run_cli("leaderboard", str(DATA), "--json")
        parts = run_cli("leaderboard", *paths, "--json")
        assert parts.returncode == 0, parts.stderr
        assert json.loads(parts.stdout) == json.loads(whole.stdout)

        compare_whole = run_cli(
            "compare", str(DATA), "--model-a", "tuned-70b", "--model-b", "baseline-70b", "--json"
        )
        compare_parts = run_cli(
            "compare", *paths, "--model-a", "tuned-70b", "--model-b", "baseline-70b", "--json"
        )
        assert json.loads(compare_parts.stdout) == json.loads(compare_whole.stdout)

    def test_a_name_is_for_a_harness_log_not_for_a_table_of_models(self) -> None:
        with pytest.raises(ValueError, match="names its models in its 'model' column"):
            load_inputs([f"mine={DATA}"])

    def test_a_path_with_an_equals_sign_is_a_path(self, tmp_path: Path) -> None:
        odd = tmp_path / "lr=3e-4.csv"
        odd.write_text("question_id,model,score\nq1,a,1\nq2,a,0\n")
        assert split_spec(str(odd)) == (None, odd)
        assert load_inputs([odd]).data.models() == ["a"]
        # A name is cut at the first `=` only when what follows is a file.
        assert split_spec(f"run={odd}") == ("run", odd)
        with pytest.raises(FileNotFoundError):
            split_spec(str(tmp_path / "missing=also-missing.csv"))

    def test_a_missing_file_is_one_line(self) -> None:
        for spec in ("nope.csv", "x=nope.csv"):
            result = run_cli("compare", spec)
            assert result.returncode != 0
            assert result.stderr.strip() == f"error: {spec}: No such file or directory"

    def test_import_writes_every_log_into_one_csv(self, tmp_path: Path) -> None:
        out = tmp_path / "all.csv"
        result = run_cli("import", "lm-eval", str(OUTPUT), "-o", str(out))
        assert result.returncode == 0, result.stderr
        assert "wrote 40 rows (2 models)" in result.stdout
        again = run_cli("compare", str(out), "--json")
        direct = run_cli("compare", str(OUTPUT), "--json")
        assert json.loads(again.stdout) == json.loads(direct.stdout)

    def test_import_still_takes_a_model_name_for_a_log_that_has_none(self, tmp_path: Path) -> None:
        out = tmp_path / "copa.csv"
        result = run_cli("import", "lm-eval", str(DUMMY_COPA), "--model", "dummy", "-o", str(out))
        assert result.returncode == 0, result.stderr
        assert "wrote 20 rows (1 model)" in result.stdout


class TestCompareDefaults:
    def test_two_models_need_no_naming_and_keep_the_input_order(self, tmp_path: Path) -> None:
        path = tmp_path / "two.csv"
        path.write_text(
            "question_id,model,score\n"
            "q1,zeta,1\nq2,zeta,1\nq3,zeta,0\nq4,zeta,1\n"
            "q1,alpha,0\nq2,alpha,1\nq3,alpha,0\nq5,alpha,1\n"
        )
        result = run_cli("compare", str(path), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        # A is the first model in the file, not the first in the alphabet.
        assert (payload["model_a"], payload["model_b"]) == ("zeta", "alpha")
        # q4 was only answered by zeta, q5 only by alpha: three questions are compared.
        assert (payload["n"], payload["n_only_a"], payload["n_only_b"]) == (3, 1, 1)

        table = run_cli("compare", str(path))
        assert "questions left out (only A / only B)" in table.stdout
        board = run_cli("leaderboard", str(path))
        assert "not scored on the same questions" in board.stdout.replace("\n", " ")

    def test_three_models_have_to_be_chosen_from(self) -> None:
        result = run_cli("compare", str(DATA))
        assert result.returncode != 0
        assert "the data has 4 models" in result.stderr and "--model-a" in result.stderr
        half = run_cli("compare", str(DATA), "--model-a", "tuned-70b")
        assert half.returncode != 0 and "both --model-a and --model-b" in half.stderr

    def test_one_model_cannot_be_compared(self) -> None:
        result = run_cli("compare", str(TINY))
        assert result.returncode != 0
        assert "the data has 1 model (" in result.stderr


class TestSummarizeClusters:
    def test_no_cluster_column_means_no_clustering_diagnostics(self, tmp_path: Path) -> None:
        # Until 0.2.0 each question counted as a cluster of one, and a 4-question file got
        # a "clustered CI" of [-0.05, 1.55].
        path = tmp_path / "plain.csv"
        path.write_text("question_id,model,score\nq1,a,1\nq2,a,0\nq3,a,1\nq4,a,1\n")
        result = run_cli("summarize", str(path), "--json")
        assert result.returncode == 0, result.stderr
        assert "clustered" not in json.loads(result.stdout)
        assert "clustering diagnostics" not in run_cli("summarize", str(path)).stdout

    def test_a_cluster_column_still_gets_them(self) -> None:
        result = run_cli("summarize", str(DATA), "--model", "tuned-70b", "--json")
        payload = json.loads(result.stdout)
        assert payload["clustered"]["n_clusters"] == 40


class TestConcat:
    def test_a_source_without_clusters_or_samples_is_filled_like_a_file_without_the_columns(self) -> None:
        plain = EvalData(question_id=["q1", "q2"], model=["a", "a"], score=[1.0, 0.0])
        rich = EvalData(
            question_id=["q1", "q2"],
            model=["b", "b"],
            score=[0.0, 0.0],
            cluster_id=["p1", "p1"],
            sample=["1", "2"],
        )
        both = concat([("plain", plain), ("rich", rich)])
        assert both.cluster_id == ["q1", "q2", "p1", "p1"]
        assert both.sample == ["0", "0", "1", "2"]
        neither = concat([("x", plain), ("y", EvalData(["q1"], ["c"], [1.0]))])
        assert neither.cluster_id is None and neither.sample is None

    def test_one_source_is_returned_as_it_is(self) -> None:
        plain = EvalData(question_id=["q1"], model=["a"], score=[1.0])
        assert concat([("only", plain)]) is plain

    def test_repeated_samples_in_two_sources_are_not_duplicates(self) -> None:
        first = EvalData(["q1"], ["a"], [1.0], sample=["1"])
        second = EvalData(["q1"], ["a"], [0.0], sample=["2"])
        assert len(concat([("one", first), ("two", second)])) == 2
        with pytest.raises(ValueError, match="already has a score"):
            concat([("one", first), ("again", first)])


class TestInspectLogs:
    def test_a_log_is_read_directly_and_can_be_named(self) -> None:
        pytest.importorskip("inspect_ai")
        loaded = load_inputs([INSPECT_LOG])
        assert loaded.data.models() == ["mockllm/model"]
        named = load_inputs([f"greedy={INSPECT_LOG}", f"sampled={INSPECT_LOG}"])
        assert named.data.models() == ["greedy", "sampled"]
        result = run_cli("compare", f"greedy={INSPECT_LOG}", f"sampled={INSPECT_LOG}", "--json")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["n"] == 5


class TestSummarizeModels:
    def test_several_models_are_not_pooled_into_one_summary(self) -> None:
        # 4 models x 200 questions used to be summarized as one sample of 800.
        result = run_cli("summarize", str(DATA), "--json")
        assert result.returncode != 0
        assert "the data has 4 models" in result.stderr and "--model" in result.stderr
        both = run_cli("summarize", str(TINY), str(RANDOM))
        assert both.returncode != 0 and "the data has 2 models" in both.stderr
        one = run_cli("summarize", str(TINY), str(RANDOM), "--model", "sshleifer/tiny-gpt2", "--json")
        assert one.returncode == 0, one.stderr
        assert json.loads(one.stdout)["n"] == 20
