"""Command-line interface: ``errorbars summarize|compare|leaderboard|power``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from errorbars.compare import paired_compare
from errorbars.io import ColumnMap, EvalData, load_csv, load_jsonl, write_csv
from errorbars.leaderboard import build_leaderboard
from errorbars.plot import forest_plot_svg
from errorbars.power import minimum_detectable_effect, questions_needed
from errorbars.stats import bootstrap_ci, is_binary, mean_ci_clt, wilson_ci

try:
    from rich.console import Console
    from rich.table import Table

    _HAS_RICH = True
except ImportError:  # pragma: no cover
    _HAS_RICH = False


def _load(path: str, columns: ColumnMap) -> EvalData:
    p = Path(path)
    if p.suffix.lower() in (".jsonl", ".ndjson"):
        return load_jsonl(p, columns)
    if p.suffix.lower() == ".csv":
        return load_csv(p, columns)
    raise SystemExit(f"error: unrecognized file extension {p.suffix!r} (use .csv or .jsonl)")


def _column_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--question-col", default="question_id")
    sp.add_argument("--model-col", default="model")
    sp.add_argument("--score-col", default="score")
    sp.add_argument("--cluster-col", default="cluster_id")
    sp.add_argument("--sample-col", default="sample")


def _columns_from(args: argparse.Namespace) -> ColumnMap:
    return ColumnMap(
        question_id=args.question_col,
        model=args.model_col,
        score=args.score_col,
        cluster_id=args.cluster_col,
        sample=args.sample_col,
    )


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _console() -> Console:
    if not _HAS_RICH:
        raise SystemExit("error: rich is required for table output; install errorbars[cli] or use --json")
    return Console()


def cmd_summarize(args: argparse.Namespace) -> None:
    data = _load(args.file, _columns_from(args))
    sub = data.filter_model(args.model) if args.model else data
    if not sub.score:
        raise SystemExit(f"error: no rows for model {args.model!r}" if args.model else "error: empty data")

    scores = sub.score
    binary = is_binary(scores)
    if args.ci == "bootstrap":
        est = bootstrap_ci(scores, confidence=args.confidence, seed=args.seed)
    elif args.ci == "wilson" or (args.ci == "auto" and binary and len(scores) < 30):
        if not binary:
            raise SystemExit("error: --ci wilson requires binary (0/1) scores")
        est = wilson_ci(int(round(sum(scores))), len(scores), confidence=args.confidence)
    else:
        est = mean_ci_clt(scores, confidence=args.confidence)

    result: dict[str, Any] = est.as_dict()
    result["model"] = args.model or "(all)"
    result["is_binary"] = binary

    cluster_info = None
    if sub.cluster_id and len(set(sub.cluster_id)) > 1:
        from errorbars.stats import cluster_robust_se, design_effect, intraclass_correlation

        icc = intraclass_correlation(scores, sub.cluster_id)
        avg_size = len(scores) / len(set(sub.cluster_id))
        deff = design_effect(icc, avg_size)
        se_c = cluster_robust_se(scores, sub.cluster_id)
        z = est.ci_high - est.mean
        z_ratio = z / est.se if est.se else 0.0
        cluster_info = {
            "clustered_se": se_c,
            "clustered_ci_low": est.mean - z_ratio * se_c,
            "clustered_ci_high": est.mean + z_ratio * se_c,
            "icc": icc,
            "design_effect": deff,
            "n_clusters": len(set(sub.cluster_id)),
        }
        result["clustered"] = cluster_info

    within_between = None
    if sub.sample and len(set(sub.sample)) > 1:
        from errorbars.stats import within_between_variance

        var_w, var_b = within_between_variance(scores, sub.question_id)
        within_between = {"var_within": var_w, "var_between": var_b}
        result["within_between"] = within_between

    if args.json:
        _print_json(result)
        return

    console = _console()
    table = Table(title=f"summarize: {result['model']}", show_header=True, header_style="bold cyan")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("n", str(est.n))
    table.add_row("mean", f"{est.mean:.4f}")
    table.add_row("SE", f"{est.se:.4f}")
    table.add_row(f"{int(args.confidence * 100)}% CI", f"[{est.ci_low:.4f}, {est.ci_high:.4f}]")
    table.add_row("method", est.method)
    console.print(table)
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
        console.print(ct)
    if within_between:
        wt = Table(title="within/between-question variance", header_style="bold magenta")
        wt.add_column("component")
        wt.add_column("variance", justify="right")
        wt.add_row("within-question (sampling noise)", f"{within_between['var_within']:.4f}")
        wt.add_row("between-question (item difficulty)", f"{within_between['var_between']:.4f}")
        console.print(wt)


def cmd_compare(args: argparse.Namespace) -> None:
    columns = _columns_from(args)
    data = _load(args.file, columns)
    a = data.filter_model(args.model_a).scores_by_question()
    b = data.filter_model(args.model_b).scores_by_question()
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        raise SystemExit("error: fewer than 2 shared question_ids between the two models")
    sa = [a[q] for q in common]
    sb = [b[q] for q in common]
    clusters = None
    cmap = data.cluster_by_question()
    if cmap and any(cmap.get(q) != q for q in common):
        clusters = [cmap.get(q, q) for q in common]
    comp = paired_compare(sa, sb, clusters=clusters, confidence=args.confidence)

    if args.json:
        _print_json(comp.as_dict())
        return

    console = _console()
    table = Table(title=f"compare: {args.model_a} vs {args.model_b}", header_style="bold cyan")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("n (shared questions)", str(comp.n))
    table.add_row(f"mean({args.model_a})", f"{comp.mean_a:.4f}")
    table.add_row(f"mean({args.model_b})", f"{comp.mean_b:.4f}")
    table.add_row("mean diff (A - B)", f"{comp.mean_diff:.4f}")
    table.add_row("paired SE", f"{comp.se_paired:.4f}")
    table.add_row(f"{int(args.confidence * 100)}% CI", f"[{comp.ci_low:.4f}, {comp.ci_high:.4f}]")
    table.add_row("p-value", f"{comp.p_value:.4g}")
    table.add_row("correlation(A, B)", f"{comp.correlation:.4f}")
    table.add_row("unpaired SE (for reference)", f"{comp.se_unpaired:.4f}")
    table.add_row("variance reduction from pairing", f"{comp.variance_reduction:.1%}")
    if comp.se_clustered is not None:
        table.add_row("clustered paired SE", f"{comp.se_clustered:.4f}")
        table.add_row(
            "clustered CI", f"[{comp.ci_low_clustered:.4f}, {comp.ci_high_clustered:.4f}]"
        )
    if comp.mcnemar is not None:
        table.add_row(
            "McNemar discordant (A wrong/B right, A right/B wrong)",
            f"{comp.mcnemar.n01} / {comp.mcnemar.n10}",
        )
        table.add_row("McNemar exact p-value", f"{comp.mcnemar.p_value:.4g}")
    console.print(table)


def cmd_leaderboard(args: argparse.Namespace) -> None:
    data = _load(args.file, _columns_from(args))
    lb = build_leaderboard(data, confidence=args.confidence, alpha=args.alpha)

    if args.plot:
        svg = forest_plot_svg(lb, title=args.plot_title)
        Path(args.plot).write_text(svg, encoding="utf-8")

    if args.json:
        _print_json(lb.as_dict())
        return

    console = _console()
    table = Table(title="leaderboard", header_style="bold cyan")
    table.add_column("rank", justify="right")
    table.add_column("model")
    table.add_column("mean", justify="right")
    table.add_column(f"{int(args.confidence * 100)}% CI", justify="right")
    table.add_column("n", justify="right")
    table.add_column("group")
    letter_of: dict[str, str] = {}
    for i, group in enumerate(lb.groups):
        letter = chr(ord("a") + i)
        for m in group:
            letter_of[m] = letter_of.get(m, "") + letter
    for rank, e in enumerate(lb.entries, start=1):
        table.add_row(
            str(rank),
            e.model,
            f"{e.mean:.4f}",
            f"[{e.ci_low:.4f}, {e.ci_high:.4f}]",
            str(e.n),
            letter_of.get(e.model, ""),
        )
    console.print(table)
    console.print(
        "[dim]Models sharing a group letter are not statistically distinguishable "
        f"(Holm-corrected paired test, alpha={args.alpha}).[/dim]"
    )

    pt = Table(title="pairwise paired tests (Holm-corrected)", header_style="bold magenta")
    pt.add_column("A")
    pt.add_column("B")
    pt.add_column("mean diff", justify="right")
    pt.add_column("p (unclustered)", justify="right")
    pt.add_column("p (used, Holm)", justify="right")
    pt.add_column("significant?")
    for pr in lb.pairwise:
        sig = "yes" if pr.p_holm < args.alpha else "no"
        pt.add_row(
            pr.model_a,
            pr.model_b,
            f"{pr.comparison.mean_diff:+.4f}",
            f"{pr.comparison.p_value:.4g}",
            f"{pr.p_holm:.4g}",
            sig,
        )
    console.print(pt)
    console.print(
        "[dim]'p (used, Holm)' is the cluster-robust paired p-value (when clusters are "
        "present) after Holm correction across all pairs; otherwise the unclustered paired p-value.[/dim]"
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
        console = _console()
        table = Table(title="power: questions needed", header_style="bold cyan")
        table.add_column("input")
        table.add_column("value", justify="right")
        table.add_row("delta", f"{args.delta}")
        table.add_row("alpha", f"{args.alpha}")
        table.add_row("power", f"{args.power}")
        table.add_row("rho (paired correlation)", f"{args.rho}")
        table.add_row("samples/question", str(args.samples_per_question))
        table.add_row("cluster design effect", f"{args.cluster_deff}")
        console.print(table)
        console.print(f"[bold green]Questions needed: {result.n_questions}[/bold green]")
    else:
        mde = minimum_detectable_effect(n_questions=args.n, **kwargs)
        payload = {"n_questions": args.n, "mde": mde, **{k: v for k, v in kwargs.items()}}
        if args.json:
            _print_json(payload)
            return
        console = _console()
        console.print(f"[bold green]Minimum detectable effect at n={args.n}: {mde:.4f}[/bold green]")


def cmd_import(args: argparse.Namespace) -> None:
    if args.adapter == "lm-eval":
        if not args.model:
            raise SystemExit("error: --model is required for the lm-eval adapter")
        from errorbars.adapters.lm_eval import load_lm_eval_samples

        data = load_lm_eval_samples(args.file, model=args.model, metric=args.metric)
    elif args.adapter == "inspect":
        try:
            from errorbars.adapters.inspect_ai import load_inspect_log
        except ImportError as exc:
            raise SystemExit(f"error: {exc}") from exc

        data = load_inspect_log(args.file, scorer=args.scorer)
    else:  # pragma: no cover - argparse `choices` already prevents this
        raise SystemExit(f"error: unknown adapter {args.adapter!r}")

    write_csv(data, args.output)
    n_models = len(data.models())
    print(f"wrote {len(data)} rows ({n_models} model{'s' if n_models != 1 else ''}) to {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="errorbars", description="Error bars for LLM evals.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summarize", help="mean, SE, and CI for one model")
    p_sum.add_argument("file")
    p_sum.add_argument("--model", default=None, help="filter to this model (default: use all rows)")
    p_sum.add_argument("--confidence", type=float, default=0.95)
    p_sum.add_argument("--ci", choices=["auto", "clt", "wilson", "bootstrap"], default="auto")
    p_sum.add_argument("--seed", type=int, default=0, help="bootstrap RNG seed")
    p_sum.add_argument("--json", action="store_true")
    _column_args(p_sum)
    p_sum.set_defaults(func=cmd_summarize)

    p_cmp = sub.add_parser("compare", help="paired comparison of two models")
    p_cmp.add_argument("file")
    p_cmp.add_argument("--model-a", required=True)
    p_cmp.add_argument("--model-b", required=True)
    p_cmp.add_argument("--confidence", type=float, default=0.95)
    p_cmp.add_argument("--json", action="store_true")
    _column_args(p_cmp)
    p_cmp.set_defaults(func=cmd_compare)

    p_lb = sub.add_parser("leaderboard", help="rank all models with pairwise tests")
    p_lb.add_argument("file")
    p_lb.add_argument("--confidence", type=float, default=0.95)
    p_lb.add_argument("--alpha", type=float, default=0.05)
    p_lb.add_argument("--plot", default=None, help="write an SVG forest plot to this path")
    p_lb.add_argument("--plot-title", default=None)
    p_lb.add_argument("--json", action="store_true")
    _column_args(p_lb)
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
    p_imp.add_argument("file", help="lm-eval samples_*.jsonl file, or an Inspect .eval/.json log")
    p_imp.add_argument("-o", "--output", required=True, help="path to write the canonical CSV to")
    p_imp.add_argument(
        "--model", default=None, help="model name to record (lm-eval adapter only; required for it)"
    )
    p_imp.add_argument(
        "--metric", default=None, help="lm-eval metric to use as the score (default: first available)"
    )
    p_imp.add_argument(
        "--scorer", default=None, help="Inspect scorer to use (default: the only one, if unambiguous)"
    )
    p_imp.set_defaults(func=cmd_import)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main(sys.argv[1:])
