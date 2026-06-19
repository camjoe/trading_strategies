from __future__ import annotations

import datetime as dt
from pathlib import Path


def modified_at(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat(timespec="seconds")


def sorted_files(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def file_ref(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    return {
        "name": path.name,
        "modifiedAt": modified_at(path),
    }
