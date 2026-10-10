"""Audit exact rank displays against every public-board pairwise decision.

Uses retained SWE-bench outcomes and the original study's exclusions. The
independent-task and repository-clustered scenarios stay separate. Neither is
an equivalence analysis; no model inference or network access is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard, rank_ranges
from errorbars.plot import forest_plot_svg

ROOT = Path(__file__).resolve().parents[2]


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def expand_ranges(text: str) -> set[int]:
    """Parse rendered ranges independently of the writer, including every interior rank."""
    if text == "-":
        return set()
    result = set()
    for segment in text.split(", "):
        ends = segment.split("-")
        result.update(range(int(ends[0]), int(ends[-1]) + 1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="6af9d95")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(["git", "rev-parse", args.baseline_ref], text=True).strip()
    modules = {}
    for name in ("leaderboard", "plot"):
        source = subprocess.check_output(["git", "show", f"{revision}:src/errorbars/{name}.py"], text=True)
        module = types.ModuleType(f"errorbars.baseline_{name}")
        sys.modules[module.__name__] = module
        exec(compile(source, f"baseline_{name}.py", "exec"), module.__dict__)
        modules[name] = module
    path = ROOT / "studies/swe-bench-verified/data/outcomes.json"
    payload = json.loads(path.read_text())
    instances = payload["instances"]
    submissions = [
        row
        for row in payload["submissions"]
        if row.get("reported") is None
        or abs(row["reported"] - 100 * row["n_resolved"] / len(instances)) <= 0.5
    ]
    qids, models, scores, clusters = [], [], [], []
    for row in submissions:
        for q, bit in zip(instances, f"{int(row['resolved'], 16):0{len(instances)}b}", strict=True):
            qids.append(q)
            models.append(row["id"])
            scores.append(float(bit))
            clusters.append(q.rsplit("-", 1)[0].replace("__", "/"))
    with (args.artifacts / "swe.csv").open("w") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["question_id", "model", "score", "cluster_id"])
        writer.writerows(zip(qids, models, scores, clusters, strict=True))
    result: dict[str, Any] = {
        "baseline_revision": revision,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "exclusions": [row["id"] for row in payload["submissions"] if row not in submissions],
        "scenarios": {},
    }
    for name, clustered in (("task-independent", False), ("repository-clustered", True)):
        data = EvalData(qids, models, scores, clusters if clustered else None)
        before = modules["leaderboard"].build_leaderboard(data)
        after = build_leaderboard(data)
        old_dict, new_dict = before.as_dict(), after.as_dict()
        # The fix changes representation, never the tests, means, intervals or cliques.
        for key in ("entries", "pairwise", "groups", "alpha"):
            assert old_dict[key] == new_dict[key], (name, key)
        unchanged_sha = digest({key: new_dict[key] for key in old_dict})
        ranks = {entry.model: rank for rank, entry in enumerate(after.entries, 1)}
        neighbors = {model: set() for model in ranks}
        for pair in after.pairwise:
            if pair.p_holm >= after.alpha:
                neighbors[pair.model_a].add(ranks[pair.model_b])
                neighbors[pair.model_b].add(ranks[pair.model_a])
        comparisons = after.rank_comparisons()
        gaps = []
        for model, actual in neighbors.items():
            rendered = rank_ranges(comparisons[model]["non_significant"])
            assert expand_ranges(rendered) == actual
            assert not comparisons[model]["untested"]
            assert expand_ranges(rank_ranges(comparisons[model]["significant"])) == (
                set(ranks.values()) - actual - {ranks[model]}
            )
            # Legacy display includes self and fills all holes between endpoints.
            envelope = actual | {ranks[model]}
            implied = set(range(min(envelope), max(envelope) + 1)) - {ranks[model]}
            if implied - actual:
                gaps.append(
                    {
                        "model": model,
                        "rank": ranks[model],
                        "old_span": f"{min(envelope)}-{max(envelope)}",
                        "significant_ranks_in_span": sorted(implied - actual),
                        "exact_display": rendered,
                    }
                )
        uses_spans = len(before.groups) > 26
        result["scenarios"][name] = {
            "models": len(after.entries),
            "questions": len(instances),
            "pairs": len(after.pairwise),
            "groups": len(after.groups),
            "baseline_cli_used_spans": uses_spans,
            "false_directed_ties_in_baseline_cli": sum(len(g["significant_ranks_in_span"]) for g in gaps)
            if uses_spans
            else 0,
            "affected_models_in_baseline_cli": len(gaps) if uses_spans else 0,
            "false_directed_ties_after": 0,
            "unchanged_analysis_sha256": unchanged_sha,
            "rank_comparisons_sha256": digest(new_dict["rank_comparisons"]),
            "span_gaps": gaps if uses_spans else [],
        }
        (args.artifacts / f"{name}-before.svg").write_text(modules["plot"].forest_plot_svg(before))
        (args.artifacts / f"{name}-after.svg").write_text(forest_plot_svg(after))
        (args.artifacts / f"{name}.json").write_text(json.dumps(new_dict, allow_nan=False) + "\n")
        print(name, {k: v for k, v in result["scenarios"][name].items() if k != "span_gaps"}, flush=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
