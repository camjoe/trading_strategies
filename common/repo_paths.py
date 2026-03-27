from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_MARKER_FILES = ("pytest.ini", "requirements.txt")


@lru_cache(maxsize=128)
def _discover_repo_root(start_dir: str) -> Path:
    current = Path(start_dir).resolve()
    for candidate in (current, *current.parents):
        if all((candidate / marker).exists() for marker in _MARKER_FILES):
            return candidate
    raise RuntimeError(f"Unable to locate repository root from: {start_dir}")


def get_repo_root(start: Path | str | None = None) -> Path:
    """Resolve repository root using env override or marker-file discovery."""
    env_root = str(os.getenv("TRADING_REPO_ROOT", "")).strip()
    if env_root:
        return Path(env_root).expanduser().resolve()

    if start is None:
        base = Path.cwd()
    else:
        base = Path(start).expanduser().resolve()

    start_dir = base if base.is_dir() else base.parent
    return _discover_repo_root(str(start_dir))
