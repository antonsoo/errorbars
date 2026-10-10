"""Forest plots for leaderboards.

The CLI writes dependency-free SVG. Python callers can also use
``forest_plot_matplotlib`` with the optional ``plot`` extra.
"""

from __future__ import annotations

from textwrap import wrap
from typing import TYPE_CHECKING

from errorbars._tables import visible
from errorbars.leaderboard import Leaderboard, rank_ranges

if TYPE_CHECKING:
    from matplotlib.figure import Figure

__all__ = ["forest_plot_svg", "forest_plot_matplotlib"]

_FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _interval_caption(leaderboard: Leaderboard) -> str:
    names = {"clustered_cr2": "CR2 with clusters", "wilson": "Wilson", "clt": "CLT"}
    levels = ", ".join(sorted({f"{100 * e.confidence:g}%" for e in leaderboard.entries}))
    methods = ", ".join(sorted({names.get(e.method, e.method) for e in leaderboard.entries}))
    return f"{levels} marginal CIs: {methods}"


def forest_plot_svg(
    leaderboard: Leaderboard,
    width: int = 640,
    row_height: int = 44,
    title: str | None = None,
) -> str:
    """Standalone forest plot with exact paired-test ranks and wrapped labels.

    ``row_height`` is a minimum: long names and disjoint rank ranges expand a
    row rather than hiding text. The point intervals remain marginal CIs.
    """
    if width < 480:
        raise ValueError("forest plot width must be at least 480 pixels")
    if row_height < 24:
        raise ValueError("forest plot row_height must be at least 24 pixels")
    entries = leaderboard.entries
    margin_left, margin_right = int(width * 0.34), int(width * 0.30)
    plot_w = width - margin_left - margin_right
    right_x = width - margin_right + 12
    model_chars = max(12, int((margin_left - 24) / 6.7))
    decision_chars = max(10, int((margin_right - 22) / 6.1))
    comparisons = leaderboard.rank_comparisons()
    rows = []
    title_lines = wrap(visible(title), width=int((width - 32) / 8)) if title else []
    margin_top = 24 + len(title_lines) * 20
    cursor = margin_top + 24
    for rank, entry in enumerate(entries, 1):
        names = wrap(visible(f"{rank}. {entry.model}"), width=model_chars)
        decisions = wrap(rank_ranges(comparisons[entry.model]["non_significant"]), width=decision_chars)
        if comparisons[entry.model]["untested"]:
            decisions += wrap(
                "not tested: " + rank_ranges(comparisons[entry.model]["untested"]), width=decision_chars
            )
        height = max(row_height, 14 * max(len(names), len(decisions)) + 16)
        rows.append((entry, names, decisions, cursor, height))
        cursor += height
    axis_y = cursor
    captions = [
        _interval_caption(leaderboard),
        f"Not separated: other ranks with Holm-adjusted p >= {leaderboard.alpha:g}. "
        "Gaps are preserved; '-' means none. Non-significance does not establish equivalence.",
        *leaderboard.warnings,
    ]
    caption_lines = [line for caption in captions for line in wrap(caption, width=int((width - 32) / 6.1))]
    height = axis_y + 36 + len(caption_lines) * 14 + 12
    lo = min(e.ci_low for e in entries)
    hi = max(e.ci_high for e in entries)
    pad = (hi - lo) * 0.1 or 0.05
    x_min, x_max = lo - pad, hi + pad

    def x(v: float) -> float:
        return margin_left + (v - x_min) / (x_max - x_min) * plot_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}" role="img">',
        f'<title>{_escape(title or "Leaderboard with paired comparisons")}</title>',
        '<desc>Models ranked by mean with marginal confidence intervals. '
        'The right column lists exact other ranks without a significant paired difference; '
        'this does not establish equivalence. Untested comparisons are identified separately.</desc>',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]

    def text(px: float, py: float, content: str, size: int = 11, anchor: str = "start") -> None:
        parts.append(
            f'<text x="{px:.1f}" y="{py:.1f}" text-anchor="{anchor}" font-size="{size}" '
            f'font-family="monospace" fill="#374151">{_escape(content)}</text>'
        )

    for i, line in enumerate(title_lines):
        text(width / 2, 22 + 20 * i, line, 13, "middle")
    text(12, margin_top + 10, "Rank / model")
    text(margin_left + plot_w / 2, margin_top + 10, "Mean / CI", 11, "middle")
    text(right_x, margin_top + 10, "Not separated: ranks", 10)
    for t in range(6):
        v = x_min + (x_max - x_min) * t / 5
        gx = x(v)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{margin_top + 24}" x2="{gx:.1f}" '
            f'y2="{axis_y}" stroke="#e5e7eb" stroke-width="1"/>'
        )
        text(gx, axis_y + 18, f"{v:.2f}", 9, "middle")

    for entry, names, decisions, top, row_h in rows:
        cy = top + row_h / 2
        parts.append('<g class="model-row">')
        parts.append(f'<title>{_escape(visible(entry.model))}</title>')
        for lines, px, size in ((names, 12, 11), (decisions, right_x, 10)):
            for i, line in enumerate(lines):
                text(px, cy - (len(lines) - 1) * 7 + 4 + 14 * i, line, size)
        x_lo, x_hi, x_mean = x(entry.ci_low), x(entry.ci_high), x(entry.mean)
        parts.append(
            f'<line x1="{x_lo:.1f}" y1="{cy:.1f}" x2="{x_hi:.1f}" y2="{cy:.1f}" '
            f'stroke="#2563eb" stroke-width="2"/>'
        )
        for edge_x in (x_lo, x_hi):
            parts.append(
                f'<line x1="{edge_x:.1f}" y1="{cy - 5:.1f}" x2="{edge_x:.1f}" '
                f'y2="{cy + 5:.1f}" stroke="#2563eb" stroke-width="2"/>'
            )
        parts.append(f'<circle cx="{x_mean:.1f}" cy="{cy:.1f}" r="4.5" fill="#1d4ed8"/>')
        text(x_mean, cy - 9, f"{entry.mean:.3f}", 10, "middle")
        parts.append('</g>')
    parts.append(
        f'<line x1="{margin_left}" y1="{axis_y}" x2="{margin_left + plot_w}" '
        f'y2="{axis_y}" stroke="#9ca3af" stroke-width="1"/>'
    )
    for i, line in enumerate(caption_lines):
        text(12, axis_y + 42 + 14 * i, line, 10)
    parts.append("</svg>")
    return "\n".join(parts)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def forest_plot_matplotlib(leaderboard: Leaderboard, title: str | None = None) -> Figure:
    """Render a forest plot with matplotlib. Requires the ``plot`` extra."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "forest_plot_matplotlib requires matplotlib (the 'plot' extra): pip install matplotlib"
        ) from exc

    entries = leaderboard.entries
    fig, ax = plt.subplots(figsize=(7, 0.6 * len(entries) + 1.2))
    ys = list(range(len(entries), 0, -1))
    means = [e.mean for e in entries]
    los = [e.mean - e.ci_low for e in entries]
    his = [e.ci_high - e.mean for e in entries]
    ax.errorbar(means, ys, xerr=[los, his], fmt="o", color="#1d4ed8", ecolor="#2563eb", capsize=4)
    ax.set_yticks(ys)
    ax.set_yticklabels([e.model for e in entries])
    caption = f"mean score\n{_interval_caption(leaderboard)}"
    for note in leaderboard.warnings:
        caption += "\n" + "\n".join(wrap(note, width=85))
    ax.set_xlabel(caption)
    if title:
        ax.set_title(title)
    ax.grid(axis="x", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig
