from __future__ import annotations

from pathlib import Path


def relative_posix(path: Path, root: Path) -> str:
    """Return *path* relative to *root* with POSIX separators."""
    return path.relative_to(root).as_posix()
