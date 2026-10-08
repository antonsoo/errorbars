"""Reproduce every number and figure in this study from data/outcomes.json.

    uv run python studies/swe-bench-verified/analyze.py

Writes results.json and figures/*.svg next to this file and prints a summary.
All statistics come from the errorbars library; this file only decides which
comparisons to make.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any

import figures
import numpy as np
from numpy.typing import NDArray

from errorbars.compare import paired_compare
from errorbars.io import EvalData
from errorbars.leaderboard import build_leaderboard, holm_correction
from errorbars.stats import (
    cluster_degrees_of_freedom,
    cluster_robust_se,
    intraclass_correlation,
    t_for_confidence,
    t_two_sided_p,
    wilson_ci,
)

HERE = Path(__file__).parent
ALPHA = 0.05
# Comparisons "near the top" are made among submissions at or above this score.
STRONG = 0.60
# A per-task file that disagrees with the submission's own reported score by more
# than this many points is not evidence about that submission.
REPORTED_TOLERANCE = 0.5
CONTROLLED_BATCH = "_mini-v2.0.0_"
GAP_BINS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10)]

Floats = NDArray[np.float64]


def load(path: Path) -> tuple[list[str], NDArray[Any], list[dict[str, Any]], Floats, list[dict[str, Any]]]:
    """Return (task ids, repository of each task, submissions, outcome matrix, excluded)."""
    data = json.loads(path.read_text())
    instances: list[str] = data["instances"]
    repo = np.array([iid.rsplit("-", 1)[0].replace("__", "/") for iid in instances])
    kept, excluded = [], []
    for sub in data["submissions"]:
        reported = sub.get("reported")
        computed = 100.0 * sub["n_resolved"] / len(instances)
        if reported is not None and abs(float(reported) - computed) > REPORTED_TOLERANCE:
            excluded.append({"id": sub["id"], "reported": float(reported), "per_task_file": computed})
        else:
            kept.append(sub)
    width = len(instances)
    matrix = np.array(
        [[float(bit) for bit in f"{int(sub['resolved'], 16):0{width}b}"] for sub in kept], dtype=float
    )
    return instances, repo, kept, matrix, excluded


def _pct(x: float) -> float:
    return round(100.0 * x, 2)


def record_progression(
    subs: list[dict[str, Any]], matrix: Floats, repo: NDArray[Any]
) -> list[dict[str, Any]]:
    """Each time the best score went up: was the new record distinguishable from the old?"""
    score = matrix.mean(axis=1)
    by_date = sorted(range(len(subs)), key=lambda k: (subs[k]["date"], -score[k]))
    best: int | None = None
    out: list[dict[str, Any]] = []
    for k in by_date:
        if best is not None and score[k] <= score[best]:
            continue
        interval = wilson_ci(int(matrix[k].sum()), matrix.shape[1])
        row: dict[str, Any] = {
            "id": subs[k]["id"],
            "name": subs[k]["name"],
            "date": subs[k]["date"],
            "checked": subs[k]["checked"],
            "score": _pct(score[k]),
            "ci": [_pct(interval.ci_low), _pct(interval.ci_high)],
        }
        if best is not None:
            comp = paired_compare(matrix[k], matrix[best], clusters=repo)
            assert comp.mcnemar is not None and comp.p_value_clustered is not None
            row.update(
                previous=_pct(score[best]),
                gain=_pct(comp.mean_diff),
                p_task=comp.p_value,
                p_mcnemar=comp.mcnemar.p_value,
                p_repo=comp.p_value_clustered,
                significant=comp.p_value < ALPHA,
            )
        out.append(row)
        best = k
    return out


def pair_table(matrix: Floats, repo: NDArray[Any], members: list[int]) -> list[dict[str, float]]:
    rows = []
    for a, b in itertools.combinations(members, 2):
        comp = paired_compare(matrix[a], matrix[b], clusters=repo)
        assert comp.se_clustered is not None and comp.p_value_clustered is not None
        assert comp.correlation is not None
        diff = matrix[a] - matrix[b]
        se_cr1 = cluster_robust_se(diff, repo, kind="CR1")
        n_repos = len(set(repo.tolist()))
        rows.append(
            {
                "gap": abs(comp.mean_diff),
                "se": comp.se_paired,
                "se_repo": comp.se_clustered,
                "rho": comp.correlation,
                "p_task": comp.p_value,
                "p_repo": comp.p_value_clustered,
                # What errorbars 0.2.4 and most packages would have printed.
                "p_repo_cr1": t_two_sided_p(comp.mean_diff / se_cr1, n_repos - 1) if se_cr1 else 1.0,
            }
        )
    return rows


def gaps_and_significance(pairs: list[dict[str, float]]) -> dict[str, Any]:
    gap = np.array([100 * p["gap"] for p in pairs])
    task = np.array([p["p_task"] < ALPHA for p in pairs])
    by_repo = np.array([p["p_repo"] < ALPHA for p in pairs])
    cr1 = np.array([p["p_repo_cr1"] < ALPHA for p in pairs])
    bins = []
    for low, high in [*GAP_BINS, (10, 100)]:
        inside = (gap >= low - 1e-9) & (gap < high - 1e-9)
        if not inside.any():
            continue
        bins.append(
            {
                "low": low,
                "high": high,
                "pairs": int(inside.sum()),
                "task_level": _pct(task[inside].mean()),
                "repo_level": _pct(by_repo[inside].mean()),
                "repo_level_cr1": _pct(cr1[inside].mean()),
            }
        )
    se = np.array([100 * p["se"] for p in pairs])
    ratio = np.array([p["se_repo"] / p["se"] for p in pairs if p["se"] > 0])
    return {
        "pairs": len(pairs),
        "bins": bins,
        "smallest_significant_gap": float(gap[task].min()),
        "largest_non_significant_gap": float(gap[~task].max()),
        "paired_se_points": {
            "median": float(np.median(se)),
            "p05": float(np.quantile(se, 0.05)),
            "p95": float(np.quantile(se, 0.95)),
        },
        "median_correlation": float(np.median([p["rho"] for p in pairs])),
        "repo_se_over_task_se": {
            "median": float(np.median(ratio)),
            "p05": float(np.quantile(ratio, 0.05)),
            "p95": float(np.quantile(ratio, 0.95)),
        },
    }


def leader_versus_rest(
    subs: list[dict[str, Any]], matrix: Floats, repo: NDArray[Any], order: list[int], depth: int
) -> list[dict[str, Any]]:
    leader = order[0]
    rows = []
    for rank, k in enumerate(order[1:depth], start=2):
        comp = paired_compare(matrix[leader], matrix[k], clusters=repo)
        assert comp.mcnemar is not None
        rows.append(
            {
                "rank": rank,
                "id": subs[k]["id"],
                "name": subs[k]["name"],
                "score": _pct(matrix[k].mean()),
                "gap": _pct(comp.mean_diff),
                "ci": [_pct(comp.ci_low), _pct(comp.ci_high)],
                "p_task": comp.p_value,
                "p_mcnemar": comp.mcnemar.p_value,
                "ci_repo": [_pct(comp.ci_low_clustered or 0.0), _pct(comp.ci_high_clustered or 0.0)],
                "p_repo": comp.p_value_clustered,
                "discordant": [comp.mcnemar.n10, comp.mcnemar.n01],
            }
        )
    return rows


def controlled_batch(
    instances: list[str], subs: list[dict[str, Any]], matrix: Floats, members: list[int]
) -> dict[str, Any]:
    """One scaffold, one release, different models: the leaderboard the library prints."""
    data = EvalData(
        question_id=[iid for _ in members for iid in instances],
        model=[subs[k]["name"] for k in members for _ in instances],
        score=[float(v) for k in members for v in matrix[k]],
    )
    board = build_leaderboard(data, alpha=ALPHA)
    letters: dict[str, str] = {}
    for index, group in enumerate(board.groups):
        for model in group:
            letters[model] = letters.get(model, "") + chr(ord("a") + index)
    return {
        "entries": [
            {
                "name": e.model,
                "score": _pct(e.mean),
                "ci": [_pct(e.ci_low), _pct(e.ci_high)],
                "groups": letters[e.model],
            }
            for e in board.entries
        ],
        "pairs": len(board.pairwise),
        "significant_unadjusted": sum(p.comparison.p_value < ALPHA for p in board.pairwise),
        "significant_holm": sum(p.p_holm < ALPHA for p in board.pairwise),
        "groups": board.groups,
    }


def repositories(repo: NDArray[Any], matrix: Floats, order: list[int], strong: list[int]) -> dict[str, Any]:
    names = sorted(set(repo.tolist()), key=lambda r: -int((repo == r).sum()))
    dof = cluster_degrees_of_freedom(repo)
    critical = t_for_confidence(0.95, dof)
    n = matrix.shape[1]
    icc = [intraclass_correlation(matrix[k], repo) for k in strong]
    ratio = [
        cluster_robust_se(matrix[k], repo) / math.sqrt(matrix[k].mean() * (1 - matrix[k].mean()) / n)
        for k in strong
    ]
    leader = order[0]
    wilson = wilson_ci(int(matrix[leader].sum()), n)
    se_repo = cluster_robust_se(matrix[leader], repo)
    mean = float(matrix[leader].mean())
    return {
        "sizes": {r: int((repo == r).sum()) for r in names},
        "largest_share": _pct(max(int((repo == r).sum()) for r in names) / n),
        "degrees_of_freedom": dof,
        "critical_value": critical,
        "icc": {
            "median": float(np.median(icc)),
            "p05": float(np.quantile(icc, 0.05)),
            "p95": float(np.quantile(icc, 0.95)),
        },
        "repo_se_over_binomial_se": {
            "median": float(np.median(ratio)),
            "p05": float(np.quantile(ratio, 0.05)),
            "p95": float(np.quantile(ratio, 0.95)),
        },
        "leader": {
            "score": _pct(mean),
            "wilson": [_pct(wilson.ci_low), _pct(wilson.ci_high)],
            "repo_clustered": [_pct(mean - critical * se_repo), _pct(mean + critical * se_repo)],
            "by_repo": {r: _pct(float(matrix[leader][repo == r].mean())) for r in names},
        },
    }


def saturation(matrix: Floats, order: list[int], top: int) -> dict[str, int]:
    solved_by = matrix[order[:top]].sum(axis=0)
    return {
        "never_solved_by_anyone": int((matrix.sum(axis=0) == 0).sum()),
        "top": top,
        "solved_by_all_top": int((solved_by == top).sum()),
        "solved_by_none_top": int((solved_by == 0).sum()),
        "contested_top": int(((solved_by > 0) & (solved_by < top)).sum()),
    }


def same_model_reruns(subs: list[dict[str, Any]], matrix: Floats) -> list[dict[str, Any]]:
    """Submissions with the same agent and the same model tags: how far apart do they land?"""
    groups: dict[tuple[Any, ...], list[int]] = {}
    for k, sub in enumerate(subs):
        if sub.get("models") and sub.get("agent"):
            groups.setdefault((sub["agent"], *sub["models"]), []).append(k)
    rows = []
    for members in groups.values():
        for a, b in itertools.combinations(members, 2):
            rows.append(
                {
                    "a": subs[a]["id"],
                    "b": subs[b]["id"],
                    "score_a": _pct(matrix[a].mean()),
                    "score_b": _pct(matrix[b].mean()),
                    "tasks_that_differ": int((matrix[a] != matrix[b]).sum()),
                }
            )
    return rows


def false_positive_rates(repo: NDArray[Any], reps: int, seed: int = 20261007) -> list[dict[str, float]]:
    """Share of true nulls rejected at 5% on this benchmark's repository sizes.

    Paired differences in {-1, 0, 1} with 14% of tasks discordant. Each
    repository has its own true advantage, drawn with mean zero and the given
    spread, so "no advantage on average over repositories" holds throughout.
    """
    names = sorted(set(repo.tolist()))
    lab = np.array([names.index(r) for r in repo])
    sizes = np.bincount(lab).astype(float)
    n, g = lab.size, sizes.size
    share = sizes / n
    onehot = np.eye(g)[lab]
    dof = cluster_degrees_of_freedom(lab)
    crit = {
        "task": t_for_confidence(0.95, n - 1),
        "cr1": t_for_confidence(0.95, g - 1),
        "cr2": t_for_confidence(0.95, dof),
    }
    rng = np.random.default_rng(seed)
    out = []
    for spread in (0.0, 0.02, 0.04, 0.08):
        rejected = dict.fromkeys(crit, 0)
        done = 0
        while done < reps:
            batch = min(2000, reps - done)
            advantage = rng.normal(0.0, spread, size=(batch, g))
            p_win = np.clip(0.07 + advantage / 2, 0, 0.5)[:, lab]
            p_loss = np.clip(0.07 - advantage / 2, 0, 0.5)[:, lab]
            u = rng.random((batch, n))
            d = np.where(u < p_win, 1.0, np.where(u < p_win + p_loss, -1.0, 0.0))
            mean = d.mean(axis=1)
            sums = (d - mean[:, None]) @ onehot
            se = {
                "task": d.std(axis=1, ddof=1) / math.sqrt(n),
                "cr1": np.sqrt((sums**2).sum(axis=1) * g / (g - 1)) / n,
                "cr2": np.sqrt((sums**2 / (1 - share)).sum(axis=1)) / n,
            }
            for key, critical in crit.items():
                rejected[key] += int((np.abs(mean) > critical * se[key]).sum())
            done += batch
        out.append({"repo_effect_sd": spread, **{k: _pct(v / reps) for k, v in rejected.items()}})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data", type=Path, default=HERE / "data" / "outcomes.json")
    parser.add_argument("--simulations", type=int, default=20000, help="replications per setting")
    args = parser.parse_args()

    instances, repo, subs, matrix, excluded = load(args.data)
    score = matrix.mean(axis=1)
    order = sorted(range(len(subs)), key=lambda k: (-score[k], subs[k]["id"]))
    strong = [k for k in order if score[k] >= STRONG]
    source = json.loads(args.data.read_text())["source"]

    records = record_progression(subs, matrix, repo)
    strong_pairs = pair_table(matrix, repo, strong)
    top20 = order[:20]
    top20_p = [paired_compare(matrix[a], matrix[b]).p_value for a, b in itertools.combinations(top20, 2)]
    adjacent = [paired_compare(matrix[order[i]], matrix[order[i + 1]]).p_value for i in range(49)]
    batch = [k for k in order if CONTROLLED_BATCH in subs[k]["id"]]
    leader_rows = leader_versus_rest(subs, matrix, repo, order, depth=25)

    results: dict[str, Any] = {
        "source": source,
        "submissions": {
            "analysed": len(subs),
            "excluded_contradictory": excluded,
            "incomplete_runs": [
                {"id": s["id"], "tasks_reported": s["n_evaluated"]} for s in subs if "n_evaluated" in s
            ],
            "checked_by_swe_bench": sum(s["checked"] is True for s in subs),
            "at_or_above_strong": len(strong),
            "strong_threshold": _pct(STRONG),
        },
        "single_score": {
            "wilson_half_width_at_leader": round(
                (lambda w: 100 * (w.ci_high - w.ci_low) / 2)(
                    wilson_ci(int(matrix[order[0]].sum()), len(instances))
                ),
                2,
            )
        },
        "records": {
            "rows": records,
            "new_records": len(records) - 1,
            "significant_task_level": sum(r.get("significant", False) for r in records),
            "significant_mcnemar": sum(r.get("p_mcnemar", 1.0) < ALPHA for r in records),
            "significant_repo_level": sum(r.get("p_repo", 1.0) < ALPHA for r in records),
        },
        "gaps": gaps_and_significance(strong_pairs),
        "leader": {"id": subs[order[0]]["id"], "name": subs[order[0]]["name"], "versus": leader_rows},
        "top20": {
            "pairs": len(top20_p),
            "significant_unadjusted": sum(p < ALPHA for p in top20_p),
            "significant_holm": sum(p < ALPHA for p in holm_correction(top20_p)),
        },
        "adjacent_ranks_top50": {"pairs": len(adjacent), "significant": sum(p < ALPHA for p in adjacent)},
        "controlled": controlled_batch(instances, subs, matrix, batch),
        "repositories": repositories(repo, matrix, order, strong),
        "saturation": saturation(matrix, order, top=20),
        "same_model_reruns": same_model_reruns(subs, matrix),
        "false_positive_rates": {
            "replications": args.simulations,
            "rows": false_positive_rates(repo, args.simulations),
        },
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=1) + "\n")

    figure_dir = HERE / "figures"
    figure_dir.mkdir(exist_ok=True)
    for theme in ("light", "dark"):
        (figure_dir / f"records-{theme}.svg").write_text(figures.records(records, theme))
        (figure_dir / f"gaps-{theme}.svg").write_text(figures.gaps(results["gaps"]["bins"], theme))
        (figure_dir / f"leader-{theme}.svg").write_text(
            figures.leader(results["leader"]["name"], _pct(score[order[0]]), leader_rows, theme)
        )

    r = results
    rec = r["records"]
    print(f"{r['submissions']['analysed']} submissions at {source['commit'][:7]}")
    print(
        f"records: {rec['significant_task_level']} of {rec['new_records']} new records were "
        f"significantly above the one they replaced (repo-level: {rec['significant_repo_level']})"
    )
    print(
        f"gaps among {len(strong)} submissions >= {STRONG:.0%}: smallest significant "
        f"{r['gaps']['smallest_significant_gap']:.1f}, largest not significant "
        f"{r['gaps']['largest_non_significant_gap']:.1f} points"
    )
    for row in r["gaps"]["bins"]:
        print(
            f"  {row['low']:>2}-{row['high']:<3} points: {row['pairs']:>4} pairs, "
            f"task-level {row['task_level']:5.1f}%  repo-level {row['repo_level']:5.1f}%  "
            f"(CR1 {row['repo_level_cr1']:5.1f}%)"
        )
    print(
        f"top 20: {r['top20']['significant_unadjusted']} of {r['top20']['pairs']} pairs significant, "
        f"{r['top20']['significant_holm']} after Holm; adjacent ranks in the top 50: "
        f"{r['adjacent_ranks_top50']['significant']} of {r['adjacent_ranks_top50']['pairs']}"
    )
    print(
        f"repositories: {r['repositories']['degrees_of_freedom']:.2f} effective degrees of freedom; "
        f"leader {r['repositories']['leader']['wilson']} by task, "
        f"{r['repositories']['leader']['repo_clustered']} by repository"
    )
    for row in r["false_positive_rates"]["rows"]:
        print(
            f"  null rejected at 5%, repo effect sd {row['repo_effect_sd']:.2f}: "
            f"task-level {row['task']:.1f}%  CR1 {row['cr1']:.1f}%  CR2 {row['cr2']:.1f}%"
        )


if __name__ == "__main__":
    main()
