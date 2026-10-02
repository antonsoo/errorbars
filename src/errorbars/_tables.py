"""Tables for the terminal: rich's when it is installed, aligned plain text when it isn't.

The commands build a :class:`Table` and hand it to an :class:`Output`. What reaches the
terminal follows three rules, each of which the first version of this broke:

- A plain ``pip install errorbars`` prints tables. ``rich`` is an extra, and without it the
  commands used to stop and ask for it; now they print the same rows as aligned text.
- A name is printed as it is. Model names come from the data (``org__model[q4_k_m]``,
  ``model:100:latest``), and rich reads ``[...]`` as style markup and ``:name:`` as an emoji,
  so a name lost its brackets or raised ``MarkupError``. Nothing here is parsed as markup.
- A name is printed whole. Written to a pipe (a CI log, a file), rich lays tables out 80
  columns wide and cuts each cell to fit, which left two models of one organisation with the
  same visible name. A pipe gets the table at its full width, and a terminal too narrow for
  it gets the long cells folded onto more lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

try:
    from rich.console import Console
    from rich.table import Table as RichTable

    HAS_RICH = True
except ImportError:  # pragma: no cover - exercised by the test that hides rich
    HAS_RICH = False

__all__ = ["HAS_RICH", "Output", "Table"]

Justify = Literal["left", "right"]

_UNBOUNDED = 100_000


@dataclass
class Table:
    """A titled table of text cells."""

    title: str
    header_style: str = "bold cyan"
    columns: list[tuple[str, Justify]] = field(default_factory=list)
    rows: list[tuple[str, ...]] = field(default_factory=list)

    def add_column(self, header: str, justify: Justify = "left") -> None:
        self.columns.append((header, justify))

    def add_row(self, *cells: str) -> None:
        self.rows.append(tuple(cells))


def plain_table(table: Table) -> str:
    """The table as aligned text: a title, a header, a rule, a line per row."""
    headers = [header for header, _ in table.columns]
    widths = [
        max(len(header), *(len(row[i]) for row in table.rows)) if table.rows else len(header)
        for i, header in enumerate(headers)
    ]

    def line(cells: tuple[str, ...] | list[str]) -> str:
        padded = [
            cell.rjust(width) if justify == "right" else cell.ljust(width)
            for cell, width, (_, justify) in zip(cells, widths, table.columns, strict=True)
        ]
        return "  ".join(padded).rstrip()

    lines = [table.title, line(headers), "  ".join("-" * width for width in widths)]
    lines.extend(line(row) for row in table.rows)
    return "\n".join(lines)


class Output:
    """Where a command's tables and notes go: standard output, through rich if it is there."""

    def __init__(self, *, use_rich: bool | None = None) -> None:
        self._rich = HAS_RICH if use_rich is None else use_rich and HAS_RICH
        self._first = True

    def _console(self, width: int | None = None) -> Console:
        # No markup, no emoji codes, no highlighting: every string is data.
        return Console(markup=False, emoji=False, highlight=False, width=width)

    def table(self, table: Table) -> None:
        if not self._rich:
            if not self._first:
                print()
            self._first = False
            print(plain_table(table))
            return
        rendered = RichTable(title=table.title, header_style=table.header_style)
        for header, justify in table.columns:
            # "fold" wraps a cell that doesn't fit; the default ("ellipsis") cuts it. Numbers
            # stay on one line, so it is the names that give way in a narrow terminal.
            rendered.add_column(header, justify=justify, overflow="fold", no_wrap=justify == "right")
        for row in table.rows:
            rendered.add_row(*row)
        console = self._console()
        if not console.is_terminal:
            # Nobody is there to resize a pipe: give the table the width it asks for. (A
            # console measures a table as no wider than itself, so ask a very wide one.)
            needed = self._console(width=_UNBOUNDED).measure(rendered).maximum
            if needed > console.width:
                console = self._console(width=needed)
        console.print(rendered)
        self._first = False

    def note(self, text: str, style: str | None = None) -> None:
        if self._rich:
            self._console().print(text, style=style)
        else:
            print(text)
