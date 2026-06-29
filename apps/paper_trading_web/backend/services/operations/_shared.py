from __future__ import annotations

from pathlib import Path

from common.files import modified_at_iso, sorted_by_mtime_desc


def modified_at(path: Path) -> str:
    return modified_at_iso(path)


def sorted_files(paths: list[Path]) -> list[Path]:
    return sorted_by_mtime_desc(paths)


def file_ref(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    return {
        "name": path.name,
        "modifiedAt": modified_at(path),
    }
