"""Shared helpers for the repository-check script tests.

Co-located rather than in ``tests/support/`` because only this suite uses them
(see ``tests/support/README.md``). The checks under ``scripts/checks/`` all work
by scanning files on disk, so every one of their test modules needs to lay out a
temporary tree first.
"""

from __future__ import annotations

from pathlib import Path


def write_file(path: Path, content: str) -> Path:
    """Write *content* to *path*, creating parent directories, and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
