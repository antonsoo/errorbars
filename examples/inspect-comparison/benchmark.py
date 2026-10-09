"""Measure imports of a synthetic expansion of the retained Inspect recording.

    uv run python examples/inspect-comparison/benchmark.py OUTPUT_DIRECTORY

Generation and the cold SDK import are outside the timing. This measures local
file parsing plus Errorbars validation, not model execution or report rendering.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from time import perf_counter

from inspect_ai.log import read_eval_log, write_eval_log

from errorbars.adapters.inspect_ai import load_inspect_log


def benchmark(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    log = read_eval_log(Path(__file__).resolve().parent / "logs/original.eval")
    originals = log.samples
    log.samples = [originals[i % len(originals)].model_copy(deep=True) for i in range(1000)]
    for i, sample in enumerate(log.samples):
        sample.id = f"stress-{i:04d}"
    log.eval.dataset.sample_ids = [sample.id for sample in log.samples]
    log.eval.dataset.samples = log.results.total_samples = log.results.completed_samples = 1000
    path = output / "synthetic-expanded.eval"
    write_eval_log(log, path)
    durations = []
    for _ in range(5):
        start = perf_counter()
        data = load_inspect_log(path)
        durations.append((perf_counter() - start) * 1000)
        assert len(data) == 1000
    result = {
        "synthetic": True, "records": 1000, "bytes": path.stat().st_size,
        "import_ms": durations, "median_ms": statistics.median(durations),
        "known_signatures": sum(h is not None for h in data.question_hash or []),
    }
    (output / "timing.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    benchmark(parser.parse_args().output)
