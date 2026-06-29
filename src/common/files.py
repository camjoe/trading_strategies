from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from pathlib import Path


def modified_at_utc(path: Path) -> dt.datetime:
    """Return a file's modified time as a timezone-aware UTC datetime."""
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)


def modified_at_iso(path: Path) -> str:
    """Return a file's modified time as an ISO timestamp in UTC."""
    return modified_at_utc(path).isoformat(timespec="seconds")


def sorted_by_mtime_desc(paths: Iterable[Path]) -> list[Path]:
    """Return paths sorted newest-first by modified time, then name."""
    return sorted(paths, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def latest_by_mtime(paths: Iterable[Path]) -> Path | None:
    """Return the newest path by modified time, or None when *paths* is empty."""
    sorted_paths = sorted_by_mtime_desc(paths)
    return sorted_paths[0] if sorted_paths else None
