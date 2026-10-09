"""Command-line interface: ``errorbars summarize|compare|leaderboard|power|import``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from errorbars import __version__
from errorbars._tables import Output, Table, visible
from errorbars.inputs import load_inputs
from errorbars.io import ColumnMap, EvalData, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.plot import forest_plot_svg
from errorbars.power import minimum_detectable_effect, questions_needed
from errorbars.review import review_comparison
from errorbars.stats import bootstrap_ci, is_binary, mean_ci_clt, prefer_wilson, wilson_ci


def _require_models(data: EvalData, *names: str) -> None:
    known = data.models()
    for name in names:
        if name not in known:
            listed = ", ".join(repr(m) for m in known[:10]) + (", ..." if len(known) > 10 else "")
            raise SystemExit(f"error: no model {name!r} in the data (models: {listed})")


def _load(args: argparse.Namespace, model: str | None = None) -> EvalData:
    """The data a command was pointed at: every FILE, read as what it is and put together."""
    try:
        loaded = load_inputs(
            args.file,
            _columns_from(args),
            model=model,
            metric=args.metric,
            filter_name=args.filter,
            scorer=args.scorer,
        )
    except ImportError as exc:
        raise SystemExit(f"error: {exc}") from exc
    for note in loaded.notes:
        print(f"note: {visible(note)}", file=sys.stderr)
    loaded.data.validate()
    return loaded.data


_FILE_HELP = (
    "one or more files or directories: errorbars CSV/JSONL, lm-eval samples_*.jsonl, "
    "Inspect .eval logs. NAME=PATH names a harness log's model"
)


def _input_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("file", nargs="+", metavar="FILE", help=_FILE_HELP)
    sp.add_argument("--question-col", default="question_id")
    sp.add_argument("--model-col", default="model")
    sp.add_argument("--score-col", default="score")
    sp.add_argument("--cluster-col", default="cluster_id")
    sp.add_argument("--sample-col", default="sample")
    sp.add_argument("--question-hash-col", default="question_hash")
    _harness_args(sp)


def _harness_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--metric", default=None, help="lm-eval metric to use as the score (default: first available)"
    )
    sp.add_argument(
        "--filter",
        default=None,
        help="lm-eval filter to use, for a task that scores each question under several (e.g. maj@8)",
    )
    sp.add_argument(
        "--scorer", default=None, help="Inspect scorer to use (default: the only one, if unambiguous)"
    )


def _columns_from(args: argparse.Namespace) -> ColumnMap:
    return ColumnMap(
        question_id=args.question_col,
        model=args.model_col,
        score=args.score_col,
        cluster_id=args.cluster_col,
        sample=args.sample_col,
        question_hash=args.question_hash_col,
    )


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str, allow_nan=False))


def _has_clusters(data: EvalData) -> bool:
    """True when an explicit assignment puts multiple questions in one cluster."""
    if not data.cluster_id:
        return False
    return len(set(data.cluster_id)) < len(set(data.question_id))


def cmd_summarize(args: argparse.Namespace) -> None:
    data = _load(args)
    if args.model:
        _require_models(data, args.model)
    elif len(data.models()) > 1:
        # Pooled, four models' answers to 200 questions would be summarized as 800 questions.
        models = data.models()
        listed = ", ".join(repr(m) for m in models[:10]) + (", ..." if len(models) > 10 else "")
        raise SystemExit(
            f"error: the data has {len(models)} models ({listed}); summarize one with --model, "
            "or rank them all with `errorbars leaderboard`"
        )
    sub = data.filter_model(args.model) if args.model else data
    if not sub.score:
        raise SystemExit(f"error: no rows for model {args.model!r}" if args.model else "error: empty data")

    question_scores = sub.scores_by_question()
    scores = list(question_scores.values())
    repeated = len(sub) > len(scores)
    binary = is_binary(scores)
    if repeated and len(scores) < 2:
        raise ValueError("need at least 2 distinct questions for repeated-generation inference")
    if repeated and args.ci == "wilson":
        raise ValueError("--ci wilson cannot treat repeated-generation question averages as binary trials")
    if args.ci == "bootstrap":
        est = bootstrap_ci(scores, confidence=args.confidence, seed=args.seed)
    elif args.ci == "wilson" or (
        args.ci == "auto"
        and binary
        and not repeated
        and prefer_wilson(int(round(sum(scores))), len(scores))
    ):
        if not binary:
            raise SystemExit("error: --ci wilson requires binary (0/1) scores")
        est = wilson_ci(int(round(sum(scores))), len(scores), confidence=args.confidence)
    else:
        est = mean_ci_clt(scores, confidence=args.confidence)

    result: dict[str, Any] = est.as_dict()
    models = sub.models()
    result["model"] = args.model or (models[0] if len(models) == 1 else "(all)")
    result["is_binary"] = binary
    result["analysis_unit"] = "question"
    result["n_questions"] = len(scores)
    result["n_observations"] = len(sub)

    cluster_info = None
    if _has_clusters(sub) and sub.cluster_id:
        from errorbars.stats import (
            cluster_degrees_of_freedom,
            cluster_robust_se,
            design_effect,
            intraclass_correlation,
            t_for_confidence,
        )

        cmap = sub.cluster_by_question()
        clusters = [cmap[qid] for qid in question_scores]
        n_clusters = len(set(clusters))
        se_c = cluster_robust_se(scores, clusters)
        icc = intraclass_correlation(scores, clusters)
        avg_size = len(scores) / n_clusters
        deff = design_effect(icc, avg_size)
        # A clustered mean rests on the clusters, not the questions: G - 1 degrees
        # of freedom when they are the same size, fewer when a few dominate.
        dof_c = cluster_degrees_of_freedom(clusters)
        t_crit = t_for_confidence(est.confidence, dof_c)
        cluster_info = {
            "clustered_se": se_c,
            "clustered_ci_low": est.mean - t_crit * se_c,
            "clustered_ci_high": est.mean + t_crit * se_c,
            "clustered_dof": dof_c,
            "icc": icc,
            "design_effect": deff,
            "n_clusters": n_clusters,
        }
        result["clustered"] = cluster_info

    within_between = None
    if repeated:
        from errorbars.stats import within_between_variance

        var_w, var_b = within_between_variance(sub.score, sub.question_id)
        within_between = {"var_within": var_w, "var_between": var_b}
        result["within_between"] = within_between

    if args.json:
        _print_json(result)
        return

    out = Output()
    table = Table(title=f"summarize: {result['model']}")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("n", str(est.n))
    if repeated:
        table.add_row("observations (generations)", str(len(sub)))
    table.add_row("mean", f"{est.mean:.4f}")
    table.add_row("SE", f"{est.se:.4f}")
    table.add_row(f"{int(args.confidence * 100)}% CI", f"[{est.ci_low:.4f}, {est.ci_high:.4f}]")
    table.add_row("method", est.method)
    out.table(table)
    if repeated:
        out.note("Each question has equal weight; generations are averaged within a question.", style="dim")
    if cluster_info:
        ct = Table(title="clustering diagnostics", header_style="bold magenta")
        ct.add_column("metric")
        ct.add_column("value", justify="right")
        ct.add_row("n clusters", str(cluster_info["n_clusters"]))
        ct.add_row("ICC", f"{cluster_info['icc']:.4f}")
        ct.add_row("design effect", f"{cluster_info['design_effect']:.3f}")
        ct.add_row("clustered SE", f"{cluster_info['clustered_se']:.4f}")
        ct.add_row(
            "clustered CI",
            f"[{cluster_info['clustered_ci_low']:.4f}, {cluster_info['clustered_ci_high']:.4f}]",
        )
        ct.add_row("degrees of freedom", f"{cluster_info['clustered_dof']:.1f}")
        out.table(ct)
    if within_between:
        wt = Table(title="within/between-question variance", header_style="bold magenta")
        wt.add_column("component")
        wt.add_column("variance", justify="right")
        wt.add_row("within-question (sampling noise)", f"{within_between['var_within']:.4f}")
        wt.add_row("between-question (item difficulty)", f"{within_between['var_between']:.4f}")
        out.table(wt)


def _models_to_compare(data: EvalData, model_a: str | None, model_b: str | None) -> tuple[str, str]:
    """The two models of a comparison: the ones named, or the only two there are, in the
    order the input gave them."""
    if model_a is None and model_b is None:
        models = data.models()
        if len(models) == 2:
            return models[0], models[1]
        listed = ", ".join(repr(m) for m in models[:10]) + (", ..." if len(models) > 10 else "")
        raise SystemExit(
            f"error: the data has {len(models)} model{'s' if len(models) != 1 else ''} ({listed}); "
            "a comparison needs two (pick them with --model-a and --model-b)"
        )
    if model_a is None or model_b is None:
        raise SystemExit("error: pass both --model-a and --model-b, or neither when there are two models")
    _require_models(data, model_a, model_b)
    return model_a, model_b


def cmd_compare(args: argparse.Namespace) -> None:
    data = _load(args)
    args.model_a, args.model_b = _models_to_compare(data, args.model_a, args.model_b)
    review = review_comparison(data, args.model_a, args.model_b, confidence=args.confidence)
    if args.html:
        if Path(args.html).suffix.lower() not in (".html", ".htm"):
            raise ValueError("--html output must end in .html or .htm")
        from errorbars.report import write_comparison_html

        write_comparison_html(review, args.html)
        print(f"wrote comparison evidence to {visible(args.html)}", file=sys.stderr)
    if review.comparison is None:
        raise ValueError(review.unavailable_reason)
    comp = review.comparison
    only_a, only_b = review.cohort["n_only_a"], review.cohort["n_only_b"]

    if args.json:
        _print_json(
            {
                "model_a": args.model_a,
                "model_b": args.model_b,
                **comp.as_dict(),
                "n_only_a": only_a,
                "n_only_b": only_b,
                "analysis_unit": "question",
                "n_observations_a": len(data.filter_model(args.model_a)),
                "n_observations_b": len(data.filter_model(args.model_b)),
                "question_identity": {
                    status: review.cohort[f"n_identity_{status}"]
                    for status in ("matching", "partial", "unavailable", "conflicting")
                },
            }
        )
        return

    out = Output()
    table = Table(title=f"compare: {args.model_a} vs {args.model_b}")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("n (shared questions)", str(comp.n))
    if only_a or only_b:
        # The two runs did not cover the same questions (a different --limit, a crashed run).
        table.add_row("questions left out (only A / only B)", f"{only_a} / {only_b}")
    table.add_row(f"mean({args.model_a})", f"{comp.mean_a:.4f}")
    table.add_row(f"mean({args.model_b})", f"{comp.mean_b:.4f}")
    table.add_row("mean diff (A - B)", f"{comp.mean_diff:.4f}")
    table.add_row("paired SE", f"{comp.se_paired:.4f}")
    table.add_row(f"{int(args.confidence * 100)}% CI", f"[{comp.ci_low:.4f}, {comp.ci_high:.4f}]")
    table.add_row("p-value", f"{comp.p_value:.4g}")
    table.add_row(
        "correlation(A, B)", f"{comp.correlation:.4f}" if comp.correlation is not None else "unavailable"
    )
    table.add_row("unpaired SE (for reference)", f"{comp.se_unpaired:.4f}")
    table.add_row(
        "variance reduction from pairing",
        f"{comp.variance_reduction:.1%}" if comp.variance_reduction is not None else "unavailable",
    )
    if comp.se_clustered is not None:
        table.add_row("clustered paired SE", f"{comp.se_clustered:.4f}")
        table.add_row("clustered CI", f"[{comp.ci_low_clustered:.4f}, {comp.ci_high_clustered:.4f}]")
        table.add_row("clustered p-value", f"{comp.p_value_clustered:.4g}")
        table.add_row(
            "clusters (degrees of freedom)", f"{comp.n_clusters} ({comp.dof_clustered:.1f})"
        )
    if comp.mcnemar is not None:
        table.add_row(
            "McNemar discordant (A wrong/B right, A right/B wrong)",
            f"{comp.mcnemar.n01} / {comp.mcnemar.n10}",
        )
        table.add_row("McNemar exact p-value", f"{comp.mcnemar.p_value:.4g}")
    out.table(table)
    out.note(
        f"Question content checks: {review.cohort['n_identity_matching']} matching, "
        f"{review.cohort['n_identity_partial']} partially checked, "
        f"{review.cohort['n_identity_unavailable']} unchecked shared ids. "
        "Matching signatures do not check scoring-rule equivalence.",
        style="dim",
    )
    for note in comp.warnings:
        out.note(note, style="yellow")


# A 12-model board has 66 pairs; past that the full pairwise table is unreadable in a terminal.
_MAX_PAIR_ROWS = 66


def cmd_leaderboard(args: argparse.Namespace) -> None:
    data = _load(args)
    lb = build_leaderboard(data, confidence=args.confidence, alpha=args.alpha)
    question_sets = {frozenset(data.filter_model(m).question_id) for m in data.models()}

    if args.plot:
        svg = forest_plot_svg(lb, title=args.plot_title)
        Path(args.plot).write_text(svg, encoding="utf-8")

    if args.json:
        _print_json(lb.as_dict())
        return

    out = Output()
    table = Table(title="leaderboard")
    table.add_column("rank", justify="right")
    table.add_column("model")
    table.add_column("mean", justify="right")
    table.add_column(f"{int(args.confidence * 100)}% CI", justify="right")
    table.add_column("interval basis")
    table.add_column("n", justify="right")
    has_repeats = any(e.n_observations != e.n for e in lb.entries)
    if has_repeats:
        table.add_column("observations", justify="right")
    # One letter per group reads well for a handful of groups. A long board has
    # dozens of overlapping ones (119 for 175 SWE-bench Verified submissions), so
    # there each model gets the span of ranks it cannot be told apart from.
    lettered = len(lb.groups) <= 26
    table.add_column("group" if lettered else "tied with ranks")
    rank_of = {e.model: rank for rank, e in enumerate(lb.entries, start=1)}
    letter_of: dict[str, str] = {}
    if lettered:
        for i, group in enumerate(lb.groups):
            letter = chr(ord("a") + i)
            for m in group:
                letter_of[m] = letter_of.get(m, "") + letter
    else:
        span: dict[str, tuple[int, int]] = {}
        for group in lb.groups:
            low, high = min(rank_of[m] for m in group), max(rank_of[m] for m in group)
            for m in group:
                known = span.get(m, (low, high))
                span[m] = (min(known[0], low), max(known[1], high))
        letter_of = {m: f"{low}-{high}" for m, (low, high) in span.items()}
    for rank, e in enumerate(lb.entries, start=1):
        cells = [
            str(rank),
            e.model,
            f"{e.mean:.4f}",
            f"[{e.ci_low:.4f}, {e.ci_high:.4f}]",
            f"CR2: {e.n_clusters} clusters, df={e.dof_clustered:.1f}"
            if e.n_clusters is not None else e.method.upper(),
            str(e.n),
        ]
        if has_repeats:
            cells.append(str(e.n_observations))
        cells.append(letter_of.get(e.model, ""))
        table.add_row(*cells)
    out.table(table)
    if any(e.n_clusters is not None for e in lb.entries):
        out.note(
            "Grouped-question intervals use CR2 standard errors and Student t with effective "
            "degrees of freedom. Each question keeps equal weight; intervals are marginal, "
            "not adjusted across models. Unclustered diagnostics remain in --json.",
            style="dim",
        )
    interval_notes: dict[str, list[str]] = {}
    for entry in lb.entries:
        for note in entry.warnings:
            interval_notes.setdefault(note, []).append(entry.model)
    for note, models in interval_notes.items():
        affected = ", ".join(models) if len(models) <= 3 else f"{len(models)} models"
        out.note(f"Intervals for {affected}: {note}", style="yellow")
    if has_repeats:
        out.note(
            "n counts questions, each weighted equally; observations counts retained generations.",
            style="dim",
        )
    if lettered:
        out.note(
            "Models sharing a group letter are not statistically distinguishable "
            f"(Holm-corrected paired test, alpha={args.alpha}).",
            style="dim",
        )
    else:
        out.note(
            "'tied with ranks' is the span of ranks a model is not statistically distinguishable "
            f"from (Holm-corrected paired test, alpha={args.alpha}); the {len(lb.groups)} "
            "overlapping groups are in --json.",
            style="dim",
        )

    shown = lb.pairwise
    title = "pairwise paired tests (Holm-corrected)"
    if len(lb.pairwise) > _MAX_PAIR_ROWS and not args.all_pairs:
        shown = [pr for pr in lb.pairwise if abs(rank_of[pr.model_a] - rank_of[pr.model_b]) == 1]
        title = f"pairwise paired tests, adjacent ranks (Holm-corrected over all {len(lb.pairwise)} pairs)"
    pt = Table(title=title, header_style="bold magenta")
    pt.add_column("A")
    pt.add_column("B")
    pt.add_column("mean diff", justify="right")
    pt.add_column("test")
    pt.add_column("p (used)", justify="right")
    pt.add_column("p (used, Holm)", justify="right")
    pt.add_column("significant?")
    for pr in shown:
        sig = "yes" if pr.p_holm < args.alpha else "no"
        pt.add_row(
            pr.model_a,
            pr.model_b,
            f"{pr.comparison.mean_diff:+.4f}",
            {"paired_t": "paired t", "clustered_t": "clustered t", "mcnemar_exact": "McNemar exact"}[pr.test],
            f"{pr.p_value_used:.4g}",
            f"{pr.p_holm:.4g}",
            sig,
        )
    out.table(pt)
    if len(shown) < len(lb.pairwise):
        out.note(
            f"Showing {len(shown)} adjacent-rank pairs of {len(lb.pairwise)}. "
            "--all-pairs prints every pair; --json always has them.",
            style="dim",
        )
    for note in dict.fromkeys(note for pr in lb.pairwise for note in pr.comparison.warnings):
        out.note(note, style="yellow")
    out.note(
        "'p (used, Holm)' adjusts the selected tests across all pairs: clustered t for "
        "dependent questions, exact McNemar for one binary score per shared question, "
        "paired t for continuous scores or repeated-generation means. Groups do not establish equivalence.",
        style="dim",
    )
    if len(question_sets) > 1:
        out.note(
            "The models were not scored on the same questions. Each mean is over that "
            "model's own questions; each paired test uses the questions its two models share.",
            style="yellow",
        )


def cmd_power(args: argparse.Namespace) -> None:
    if args.n is not None and args.delta is not None:
        raise SystemExit("error: pass either --delta (solve for n) or --n (solve for MDE), not both")
    if args.n is None and args.delta is None:
        raise SystemExit("error: pass one of --delta or --n")

    kwargs: dict[str, Any] = dict(
        baseline_accuracy=args.baseline,
        variance=args.variance,
        alpha=args.alpha,
        power=args.power,
        rho=args.rho,
        samples_per_question=args.samples_per_question,
        cluster_design_effect=args.cluster_deff,
    )

    if args.delta is not None:
        result = questions_needed(delta=args.delta, **kwargs)
        payload = result.as_dict()
        if args.json:
            _print_json(payload)
            return
        out = Output()
        table = Table(title="power: questions needed")
        table.add_column("input")
        table.add_column("value", justify="right")
        table.add_row("delta", f"{args.delta}")
        table.add_row("alpha", f"{args.alpha}")
        table.add_row("power", f"{args.power}")
        table.add_row("rho (paired correlation)", f"{args.rho}")
        table.add_row("samples/question", str(args.samples_per_question))
        table.add_row("cluster design effect", f"{args.cluster_deff}")
        out.table(table)
        out.note(f"Questions needed: {result.n_questions}", style="bold green")
    else:
        mde = minimum_detectable_effect(n_questions=args.n, **kwargs)
        payload = {"n_questions": args.n, "mde": mde, **{k: v for k, v in kwargs.items()}}
        if args.json:
            _print_json(payload)
            return
        out = Output()
        out.note(f"Minimum detectable effect at n={args.n}: {mde:.4f}", style="bold green")


def cmd_import(args: argparse.Namespace) -> None:
    # The adapter word is kept for the commands people already have; what each file is, is
    # read from the file.
    args.question_col, args.model_col, args.score_col = "question_id", "model", "score"
    args.cluster_col, args.sample_col = "cluster_id", "sample"
    args.question_hash_col = "question_hash"
    data = _load(args, model=args.model)

    write_csv(data, args.output)
    n_models = len(data.models())
    print(f"wrote {len(data)} rows ({n_models} model{'s' if n_models != 1 else ''}) to {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="errorbars", description="Error bars for LLM evals.")
    parser.add_argument("--version", action="version", version=f"errorbars {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summarize", help="mean, SE, and CI for one model")
    p_sum.add_argument("--model", default=None, help="filter to this model (default: use all rows)")
    p_sum.add_argument("--confidence", type=float, default=0.95)
    p_sum.add_argument("--ci", choices=["auto", "clt", "wilson", "bootstrap"], default="auto")
    p_sum.add_argument("--seed", type=int, default=0, help="bootstrap RNG seed")
    p_sum.add_argument("--json", action="store_true")
    _input_args(p_sum)
    p_sum.set_defaults(func=cmd_summarize)

    p_cmp = sub.add_parser("compare", help="paired comparison of two models")
    p_cmp.add_argument("--model-a", default=None, help="default: the first of the two models in the input")
    p_cmp.add_argument("--model-b", default=None, help="default: the second")
    p_cmp.add_argument("--confidence", type=float, default=0.95)
    p_cmp.add_argument("--json", action="store_true")
    p_cmp.add_argument(
        "--html", default=None, metavar="PATH", help="write a standalone comparison evidence report"
    )
    _input_args(p_cmp)
    p_cmp.set_defaults(func=cmd_compare)

    p_lb = sub.add_parser("leaderboard", help="rank all models with pairwise tests")
    p_lb.add_argument("--confidence", type=float, default=0.95)
    p_lb.add_argument("--alpha", type=float, default=0.05)
    p_lb.add_argument("--plot", default=None, help="write an SVG forest plot to this path")
    p_lb.add_argument("--plot-title", default=None)
    p_lb.add_argument("--json", action="store_true")
    p_lb.add_argument(
        "--all-pairs",
        action="store_true",
        help=f"print every pairwise test (default: adjacent ranks only past {_MAX_PAIR_ROWS} pairs)",
    )
    _input_args(p_lb)
    p_lb.set_defaults(func=cmd_leaderboard)

    p_pow = sub.add_parser("power", help="sample-size / minimum-detectable-effect planning")
    p_pow.add_argument("--delta", type=float, default=None, help="effect size to detect (solve for n)")
    p_pow.add_argument("--n", type=int, default=None, help="number of questions (solve for MDE)")
    p_pow.add_argument("--baseline", type=float, default=None, help="baseline accuracy (binary metric)")
    p_pow.add_argument(
        "--variance", type=float, default=None, help="raw per-sample variance (continuous metric)"
    )
    p_pow.add_argument("--alpha", type=float, default=0.05)
    p_pow.add_argument("--power", type=float, default=0.8)
    p_pow.add_argument(
        "--rho", type=float, default=0.0, help="correlation between models' per-question scores"
    )
    p_pow.add_argument("--samples-per-question", type=int, default=1)
    p_pow.add_argument("--cluster-deff", type=float, default=1.0, help="cluster design effect (>=1)")
    p_pow.add_argument("--json", action="store_true")
    p_pow.set_defaults(func=cmd_power)

    p_imp = sub.add_parser(
        "import", help="convert an lm-evaluation-harness or Inspect AI log to the canonical CSV"
    )
    p_imp.add_argument("adapter", choices=["lm-eval", "inspect"])
    p_imp.add_argument("file", nargs="+", metavar="FILE", help=_FILE_HELP)
    p_imp.add_argument("-o", "--output", required=True, help="path to write the canonical CSV to")
    p_imp.add_argument(
        "--model",
        default=None,
        help="model name for every log given (default: the one each log names; NAME=PATH names one)",
    )
    _harness_args(p_imp)
    p_imp.set_defaults(func=cmd_import)

    return parser


def _text_streams() -> None:
    """Make stdout and stderr able to carry any text.

    A pipe or a file gets UTF-8: before 3.15, Python on Windows gives it the system's code
    page, where a model name outside it raised ``UnicodeEncodeError``. A terminal keeps its own encoding
    and shows a character it cannot encode as an escape.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # replaced by something that isn't a text file
            continue
        if stream.isatty():
            reconfigure(errors="backslashreplace")
        else:
            reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _text_streams()
    try:
        _run(args)
    except SystemExit as exc:
        # The messages quote models, files and values from the data.
        if isinstance(exc.code, str):
            raise SystemExit(visible(exc.code)) from exc.__cause__
        raise


def _run(args: argparse.Namespace) -> None:
    try:
        args.func(args)
    except UnicodeDecodeError as exc:
        raise SystemExit(f"error: the input is not UTF-8 text ({exc})") from exc
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc
    except OSError as exc:
        # A missing or unreadable file is the user's to fix: name it, without a traceback.
        where = f"{exc.filename}: " if exc.filename else ""
        raise SystemExit(f"error: {where}{exc.strerror or exc}") from exc


if __name__ == "__main__":
    main(sys.argv[1:])
