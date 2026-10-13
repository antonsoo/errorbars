"""Complete file exports without replacing their source evidence."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


def _check_destination(destination: Path, protected: tuple[Path, ...]) -> None:
    if destination.is_symlink():
        raise ValueError("output must not be a symbolic link; choose a separate regular file")
    resolved = destination.resolve()
    for source in protected:
        if resolved == source.resolve() or (
            destination.exists() and source.exists() and destination.samefile(source)
        ):
            raise ValueError("output must not replace an input file or an alias of one")
    if destination.exists() and not destination.is_file():
        raise ValueError("output must be a regular file")


@contextmanager
def atomic_text_output(
    path: str | Path, *, protected: Iterable[str | Path] = (), newline: str | None = None,
) -> Iterator[IO[str]]:
    """Commit a flushed sibling file; failures leave an earlier output intact.

    Temporary files are private (0600 on POSIX). This does not lock concurrent
    writers or guarantee directory durability across a whole-machine power loss.
    """
    destination = Path(path)
    sources = tuple(dict.fromkeys(Path(source) for source in protected))
    _check_destination(destination, sources)
    temporary: Path | None = None
    try:
        # A destination may already use the filesystem's full filename length.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline=newline, prefix=".errorbars-output-",
            suffix=".tmp", dir=destination.parent, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            yield handle.file
            handle.flush()
            os.fsync(handle.fileno())
        _check_destination(destination, sources)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
