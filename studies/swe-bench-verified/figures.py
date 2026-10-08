"""The study's three figures as dependency-free SVG, in a light and a dark variant.

Marks follow one small rule set: 2px lines, dots with a ring in the surface
colour, hairline grid, text in ink (never in a series colour), and one accent
hue for the points the figure is about with grey for the rest.
"""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
THEMES: dict[str, dict[str, str]] = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "accent": "#2a78d6",
        "second": "#eb6834",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "accent": "#3987e5",
        "second": "#d95926",
    },
}
WIDTH = 880


class _Svg:
    def __init__(self, height: int, theme: str, title: str, subtitle: str) -> None:
        self.c = THEMES[theme]
        self.height = height
        self.parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" '
            f'height="{height}" role="img" font-family="{FONT}">',
            f"<title>{escape(title)}</title>",
            f'<rect width="{WIDTH}" height="{height}" fill="{self.c["surface"]}"/>',
        ]
        self.text(24, 30, title, size=16, weight=600)
        self.text(24, 50, subtitle, size=12.5, fill="secondary")

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        size: float = 12,
        fill: str = "ink",
        anchor: str = "start",
        weight: int = 400,
        numeric: bool = False,
    ) -> None:
        extra = ' font-variant-numeric="tabular-nums"' if numeric else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{self.c[fill]}" text-anchor="{anchor}"{extra}>{escape(content)}</text>'
        )

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str, width: float = 1) -> None:
        self.parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{self.c[stroke]}" '
            f'stroke-width="{width}" stroke-linecap="round"/>'
        )

    def dot(self, x: float, y: float, fill: str, tooltip: str, radius: float = 4.5) -> None:
        self.parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{self.c[fill]}" '
            f'stroke="{self.c["surface"]}" stroke-width="2"><title>{escape(tooltip)}</title></circle>'
        )

    def legend(self, y: float, items: list[tuple[str, str]]) -> None:
        x = 24.0
        for fill, label in items:
            self.parts.append(f'<circle cx="{x + 5:.1f}" cy="{y - 4:.1f}" r="4.5" fill="{self.c[fill]}"/>')
            self.text(x + 16, y, label, size=12.5, fill="secondary")
            # No text metrics here: 6.4px per character is a safe average at this size.
            x += 16 + 6.4 * len(label) + 28

    def render(self) -> str:
        return "\n".join([*self.parts, "</svg>"]) + "\n"


def _clip(name: str, limit: int) -> str:
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def records(rows: list[dict[str, Any]], theme: str) -> str:
    """The top score over time; a dot for each submission that raised it."""
    significant = sum(r.get("significant", False) for r in rows)
    svg = _Svg(
        440,
        theme,
        "Every new SWE-bench Verified record, and whether it was distinguishable from the last",
        "Share of the 500 tasks resolved by each submission that raised the top score, with a 95% interval.",
    )
    svg.legend(
        78,
        [
            ("accent", f"significantly above the record it replaced ({significant})"),
            ("muted", f"within noise of it ({len(rows) - 1 - significant})"),
        ],
    )
    left, right, top, bottom = 56, WIDTH - 28, 100, 440 - 40
    start, end = date(2023, 9, 1), date(2026, 2, 1)

    def x_of(day: str) -> float:
        return left + (date.fromisoformat(day) - start).days / (end - start).days * (right - left)

    def y_of(percent: float) -> float:
        return bottom - percent / 90.0 * (bottom - top)

    for tick in (0, 20, 40, 60, 80):
        svg.line(left, y_of(tick), right, y_of(tick), "grid")
        svg.text(left - 8, y_of(tick) + 4, f"{tick}%", size=11.5, fill="muted", anchor="end", numeric=True)
    for year, month, label in (
        (2024, 1, "Jan 2024"),
        (2024, 7, "Jul 2024"),
        (2025, 1, "Jan 2025"),
        (2025, 7, "Jul 2025"),
        (2026, 1, "Jan 2026"),
    ):
        x = x_of(date(year, month, 1).isoformat())
        svg.line(x, bottom, x, bottom + 5, "axis")
        svg.text(x, bottom + 20, label, size=11.5, fill="muted", anchor="middle")
    svg.line(left, bottom, right, bottom, "axis")

    points = [(x_of(r["date"]), y_of(r["score"])) for r in rows]
    path = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for x, y in points[1:]:
        path += f" H{x:.1f} V{y:.1f}"
    path += f" H{right:.1f}"
    svg.parts.append(
        f'<path d="{path}" fill="none" stroke="{svg.c["axis"]}" stroke-width="2" stroke-linejoin="round"/>'
    )
    for r, (x, _) in zip(rows, points, strict=True):
        colour = "accent" if r.get("significant") else "muted"
        svg.line(x, y_of(r["ci"][0]), x, y_of(r["ci"][1]), colour, 1.5)
    for r, (x, y) in zip(rows, points, strict=True):
        if "gain" in r:
            tip = (
                f"{r['date']}  {r['name']}: {r['score']:.1f}%, +{r['gain']:.1f} over the previous "
                f"record, p = {r['p_task']:.3f}"
            )
        else:
            tip = f"{r['date']}  {r['name']}: {r['score']:.1f}% (first entry)"
        svg.dot(x, y, "accent" if r.get("significant") else "muted", tip)
        if r.get("significant"):
            gain = f"+{r['gain']:.1f}"
            svg.text(x - 9, y - 7, gain, size=11.5, fill="secondary", anchor="end", numeric=True)
    last_x, last_y = points[-1]
    svg.text(last_x + 10, last_y - 9, f"{rows[-1]['score']:.1f}%", size=12.5, weight=600, numeric=True)
    return svg.render()


def gaps(bins: list[dict[str, Any]], theme: str) -> str:
    """Share of pairs a test calls different, by the size of the gap between them."""
    shown = [b for b in bins if b["high"] <= 10]
    svg = _Svg(
        400,
        theme,
        "How big a gap has to be before a paired test can see it",
        "Share of pairs of submissions (both at or above 60%) that differ at the 5% level, by their gap.",
    )
    svg.legend(
        78,
        [
            ("accent", "tasks as the sample (paired t-test)"),
            ("second", "repositories as the sample (clustered, 3.3 degrees of freedom)"),
        ],
    )
    left, right, top, bottom = 56, WIDTH - 150, 104, 400 - 58
    step = (right - left) / len(shown)

    def x_of(index: int) -> float:
        return left + step * (index + 0.5)

    def y_of(percent: float) -> float:
        return bottom - percent / 100.0 * (bottom - top)

    for tick in (0, 25, 50, 75, 100):
        svg.line(left, y_of(tick), right, y_of(tick), "grid")
        svg.text(left - 8, y_of(tick) + 4, f"{tick}%", size=11.5, fill="muted", anchor="end", numeric=True)
    svg.line(left, bottom, right, bottom, "axis")
    for i, b in enumerate(shown):
        svg.text(x_of(i), bottom + 19, f"{b['low']}–{b['high']}", size=11.5, fill="muted", anchor="middle")
    svg.text(
        (left + right) / 2,
        bottom + 42,
        "gap between two submissions, in points",
        size=12,
        fill="secondary",
        anchor="middle",
    )
    for key, colour, label in (
        ("repo_level", "second", "repositories"),
        ("task_level", "accent", "tasks"),
    ):
        coordinates = [(x_of(i), y_of(b[key])) for i, b in enumerate(shown)]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in coordinates)
        svg.parts.append(
            f'<path d="{d}" fill="none" stroke="{svg.c[colour]}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for b, (x, y) in zip(shown, coordinates, strict=True):
            svg.dot(
                x,
                y,
                colour,
                f"gap {b['low']}–{b['high']} points: {b[key]:.1f}% of {b['pairs']} pairs ({label})",
                radius=4,
            )
        end_x, end_y = coordinates[-1]
        svg.text(end_x + 12, end_y + 4, f"{label}: {shown[-1][key]:.0f}%", size=12, fill="secondary")
    return svg.render()


def leader(name: str, score: float, rows: list[dict[str, Any]], theme: str) -> str:
    """The leader's paired advantage over each following rank, with its interval."""
    row_height = 22
    top = 112
    height = top + row_height * len(rows) + 52
    ahead = sum(r["p_task"] < 0.05 for r in rows)
    svg = _Svg(
        height,
        theme,
        "How far down the leaderboard before the leader is clearly ahead",
        f"{_clip(name, 60)} ({score:.1f}%) minus each following rank: paired difference, 95% interval.",
    )
    svg.legend(
        78,
        [
            ("muted", f"not distinguishable from the leader ({len(rows) - ahead})"),
            ("accent", f"leader significantly ahead ({ahead})"),
        ],
    )
    left, right = 392, WIDTH - 28
    low, high = -4.0, 12.0
    bottom = top + row_height * len(rows)

    def x_of(points: float) -> float:
        return left + (points - low) / (high - low) * (right - left)

    for tick in range(-4, 13, 2):
        svg.line(x_of(tick), top - 6, x_of(tick), bottom, "grid")
        label = f"{tick:+d}".replace("-", "\u2212") if tick else "0"
        svg.text(x_of(tick), bottom + 18, label, size=11.5, fill="muted", anchor="middle")
    svg.line(x_of(0), top - 6, x_of(0), bottom, "muted")
    svg.text(
        (left + right) / 2,
        bottom + 40,
        "leader's advantage, in points",
        size=12,
        fill="secondary",
        anchor="middle",
    )
    for i, r in enumerate(rows):
        y = top + row_height * (i + 0.5)
        colour = "accent" if r["p_task"] < 0.05 else "muted"
        svg.text(40, y + 4, str(r["rank"]), size=12, fill="muted", anchor="end", numeric=True)
        svg.text(52, y + 4, _clip(r["name"], 38), size=12, fill="secondary")
        svg.text(left - 16, y + 4, f"{r['score']:.1f}", size=12, fill="ink", anchor="end", numeric=True)
        svg.line(x_of(r["ci"][0]), y, x_of(r["ci"][1]), y, colour, 2)
        svg.dot(
            x_of(r["gap"]),
            y,
            colour,
            f"rank {r['rank']}  {r['name']}: leader ahead by {r['gap']:.1f} points "
            f"[{r['ci'][0]:.1f}, {r['ci'][1]:.1f}], p = {r['p_task']:.3f}",
        )
    return svg.render()
