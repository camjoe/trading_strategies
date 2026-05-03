from __future__ import annotations

from pathlib import Path

from ._shared import modified_at, sorted_files


def list_artifacts(
    directory: Path,
    *,
    limit: int = 6,
    suffixes: tuple[str, ...] | None = None,
) -> list[dict[str, object]]:
    if not directory.exists():
        return []
    files = [path for path in directory.iterdir() if path.is_file()]
    if suffixes is not None:
        files = [path for path in files if path.suffix.lower() in suffixes]
    artifacts = sorted_files(files)[:limit]
    return [
        {
            "name": artifact.name,
            "modifiedAt": modified_at(artifact),
            "sizeBytes": int(artifact.stat().st_size),
        }
        for artifact in artifacts
    ]
