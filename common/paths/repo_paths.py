from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def _discover_repo_root_via_git(start_dir: str) -> Path | None:
    completed = subprocess.run(
        ["git", "-C", start_dir, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return None

    raw_root = completed.stdout.strip()
    if not raw_root:
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
    raise RuntimeError(
        "Unable to determine repository root via git from "
        f"{start_dir}."
    )
