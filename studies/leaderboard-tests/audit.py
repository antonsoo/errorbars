"""Audit leaderboard test selection on retained real outcomes and an exact null.

The existing SWE-bench study's exclusions are preserved. Task-independent and
repository-clustered analyses are reported separately; independence is not
claimed for SWE-bench tasks. No data are downloaded and no models are run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import types
from dataclasses import asdict
from pathlib import Path

from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

from errorbars.compare import paired_compare
from errorbars.inputs import load_inputs
from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="26bcc3f")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "rev-parse", args.baseline_ref], text=True).strip()
    source = subprocess.check_output(["git", "show", f"{revision}:src/errorbars/leaderboard.py"], text=True)
    legacy = types.ModuleType("errorbars.leaderboard_baseline")
    sys.modules[legacy.__name__] = legacy
    exec(compile(source, "leaderboard_baseline.py", "exec"), legacy.__dict__)
    started = time.monotonic()
    null = []
    for n in (2, 3, 4, 5, 6, 8, 10, 20, 40):
        old_reject = new_reject = 0.0
        for successes in range(n + 1):
            a = [1.0] * successes + [0.0] * (n - successes)
            b = [1 - x for x in a]
            comparison = paired_compare(a, b)
            exact = mcnemar([[0, n - successes], [successes, 0]], exact=True).pvalue
            assert comparison.mcnemar is not None
            assert math.isclose(comparison.mcnemar.p_value, exact, abs_tol=1e-14)
            probability = math.comb(n, successes) / 2**n
            old_reject += probability * (comparison.p_value < 0.05)
            new_reject += probability * (exact < 0.05)
        assert new_reject <= 0.05
        null.append(
            {
                "discordant_questions": n,
                "paired_t_rejection_probability": old_reject,
                "exact_rejection_probability": new_reject,
            }
        )
    path = ROOT / "studies/swe-bench-verified/data/outcomes.json"
    payload = json.loads(path.read_text())
    instances = payload["instances"]
    submissions, excluded = [], []
    for row in payload["submissions"]:
        score = 100 * row["n_resolved"] / len(instances)
        if row.get("reported") is not None and abs(float(row["reported"]) - score) > 0.5:
            excluded.append(row["id"])
        else:
            submissions.append(row)
    qids, models, scores, clusters = [], [], [], []
    for row in submissions:
        bits = f"{int(row['resolved'], 16):0{len(instances)}b}"
        assert len(bits) == len(instances)
        for q, bit in zip(instances, bits, strict=True):
            qids.append(q)
            models.append(row["id"])
            scores.append(float(bit))
            clusters.append(q.rsplit("-", 1)[0].replace("__", "/"))
    scenarios = {
        "swe_task_independent": EvalData(qids, models, scores),
        "swe_repository_clustered": EvalData(qids, models, scores, clusters),
        "lm_eval_copa": load_inputs([ROOT / "tests/fixtures/lm_eval_output"]).data,
    }
    results = {}
    for name, data in scenarios.items():
        before = legacy.build_leaderboard(data)
        after = build_leaderboard(data)
        interval_changes = []
        for old_entry, new_entry in zip(before.entries, after.entries, strict=True):
            for field in ("model", "mean", "n", "n_observations"):
                assert getattr(old_entry, field) == getattr(new_entry, field)
            if new_entry.n_clusters is None:
                for field in ("se", "ci_low", "ci_high", "method"):
                    assert getattr(old_entry, field) == getattr(new_entry, field)
            else:
                interval_changes.append({"before": asdict(old_entry), "after": new_entry.as_dict()})
        expected = multipletests([p.p_value_used for p in after.pairwise], method="holm")[1]
        assert all(
            math.isclose(p.p_holm, target, abs_tol=1e-13)
            for p, target in zip(after.pairwise, expected, strict=True)
        )
        changed = []
        for old, new in zip(before.pairwise, after.pairwise, strict=True):
            assert (old.model_a, old.model_b) == (new.model_a, new.model_b)
            if (old.p_holm < 0.05) != (new.p_holm < 0.05):
                changed.append({"before": old.as_dict(), "after": new.as_dict()})
        results[name] = {
            "models": len(after.entries),
            "questions": len(set(data.question_id)),
            "pairs": len(after.pairwise),
            "before_groups": len(before.groups),
            "after_groups": len(after.groups),
            "before_significant": sum(p.p_holm < 0.05 for p in before.pairwise),
            "after_significant": sum(p.p_holm < 0.05 for p in after.pairwise),
            "changed_decisions": changed,
            "interval_changes": interval_changes,
            "methods": sorted({p.test for p in after.pairwise}),
        }
        if name == "swe_repository_clustered":
            assert not changed and before.groups == after.groups
            assert [p.p_holm for p in before.pairwise] == [p.p_holm for p in after.pairwise]
        if name == "lm_eval_copa":
            results[name]["before"] = before.as_dict()
            results[name]["after"] = after.as_dict()
        print(
            name,
            {
                k: v
                for k, v in results[name].items()
                if k not in ("changed_decisions", "interval_changes", "before", "after")
            },
            "changed",
            len(changed),
            flush=True,
        )
    inputs = [path, *sorted((ROOT / "tests/fixtures/lm_eval_output").glob("*/*"))]
    result = {
        "baseline_revision": revision,
        "baseline_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "current_source_sha256": hashlib.sha256(
            (ROOT / "src/errorbars/leaderboard.py").read_bytes()
        ).hexdigest(),
        "input_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs
        },
        "swe_exclusions": excluded,
        "conditional_null": null,
        "scenarios": results,
        "seconds": round(time.monotonic() - started, 3),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
