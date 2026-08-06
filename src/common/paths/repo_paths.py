from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from common.git import run_git


@lru_cache(maxsize=128)
def _discover_repo_root_via_git(start_dir: str) -> Path | None:
    raw_root = run_git("rev-parse", "--show-toplevel", cwd=start_dir)
    if raw_root is None:
        return None

    candidate = Path(raw_root).expanduser().resolve()
    if not candidate.is_dir():
        return None
    return candidate


def get_repo_root(start: Path | str | None = None) -> Path:
    """Resolve repository root using git top-level discovery."""

    if start is None:
        base = Path.cwd()
    else:
        base = Path(start).expanduser().resolve()

    start_dir = base if base.is_dir() else base.parent
    git_root = _discover_repo_root_via_git(str(start_dir))
    if git_root is not None:
        return git_root
    raise RuntimeError(f"Unable to determine repository root via git from {start_dir}.")
