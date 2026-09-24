"""Forest plots for leaderboards.

A dependency-free SVG writer always works; ``forest_plot_matplotlib`` is
used automatically by the CLI when matplotlib is installed (the ``plot``
extra) and a raster/PDF output is requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from errorbars.leaderboard import Leaderboard

if TYPE_CHECKING:
    from matplotlib.figure import Figure

__all__ = ["forest_plot_svg", "forest_plot_matplotlib"]

_FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def forest_plot_svg(
    leaderboard: Leaderboard,
    width: int = 640,
    row_height: int = 44,
    title: str | None = None,
) -> str:
    """Render a forest plot (mean + CI per model) as a standalone SVG string."""
    entries = leaderboard.entries
    n = len(entries)
    margin_left, margin_right, margin_top, margin_bottom = 160, 40, 50 if title else 20, 30
    plot_h = n * row_height
    height = margin_top + plot_h + margin_bottom
    plot_w = width - margin_left - margin_right

    lo = min(e.ci_low for e in entries)
    hi = max(e.ci_high for e in entries)
    pad = (hi - lo) * 0.1 or 0.05
    x_min, x_max = lo - pad, hi + pad

    def x(v: float) -> float:
        return margin_left + (v - x_min) / (x_max - x_min) * plot_w

    def y(i: int) -> float:
        return margin_top + i * row_height + row_height / 2

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')
    if title:
        parts.append(
            f'<text x="{width / 2}" y="24" text-anchor="middle" font-size="15" '
            f'font-weight="600" fill="#111827">{_escape(title)}</text>'
        )

    # gridlines + x axis ticks
    n_ticks = 5
    for t in range(n_ticks + 1):
        v = x_min + (x_max - x_min) * t / n_ticks
        gx = x(v)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{margin_top}" x2="{gx:.1f}" '
            f'y2="{margin_top + plot_h}" stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{gx:.1f}" y="{margin_top + plot_h + 18}" text-anchor="middle" '
            f'font-size="10" fill="#6b7280">{v:.3f}</text>'
        )

    groups = leaderboard.groups
    letter_of: dict[str, str] = {}
    for i, group in enumerate(groups):
        letter = chr(ord("a") + i)
        for m in group:
            letter_of[m] = letter_of.get(m, "") + letter

    for i, e in enumerate(entries):
        cy = y(i)
        parts.append(
            f'<text x="{margin_left - 12}" y="{cy + 4:.1f}" text-anchor="end" '
            f'font-size="12" fill="#111827">{_escape(e.model)}</text>'
        )
        x_lo, x_hi, x_mean = x(e.ci_low), x(e.ci_high), x(e.mean)
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
        label = f"{e.mean:.3f}"
        if letter_of.get(e.model):
            label += f"  ({letter_of[e.model]})"
        parts.append(
            f'<text x="{x_hi + 10:.1f}" y="{cy + 4:.1f}" font-size="11" '
            f'fill="#374151">{_escape(label)}</text>'
        )

    parts.append(
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" '
        f'y2="{margin_top + plot_h}" stroke="#9ca3af" stroke-width="1"/>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def forest_plot_matplotlib(leaderboard: Leaderboard, title: str | None = None) -> Figure:
    """Render a forest plot with matplotlib. Requires the ``plot`` extra."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise ImportError("forest_plot_matplotlib requires matplotlib: pip install errorbars[plot]") from exc

    entries = leaderboard.entries
    fig, ax = plt.subplots(figsize=(7, 0.6 * len(entries) + 1.2))
    ys = list(range(len(entries), 0, -1))
    means = [e.mean for e in entries]
    los = [e.mean - e.ci_low for e in entries]
    his = [e.ci_high - e.mean for e in entries]
    ax.errorbar(means, ys, xerr=[los, his], fmt="o", color="#1d4ed8", ecolor="#2563eb", capsize=4)
    ax.set_yticks(ys)
    ax.set_yticklabels([e.model for e in entries])
    ax.set_xlabel("mean score")
    if title:
        ax.set_title(title)
    ax.grid(axis="x", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig
