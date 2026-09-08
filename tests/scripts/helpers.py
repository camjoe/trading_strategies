"""Shared helpers for the repository-check script tests."""

from __future__ import annotations

from pathlib import Path


def write_file(path: Path, content: str) -> Path:
    """Write *content* to *path*, creating parent directories, and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
