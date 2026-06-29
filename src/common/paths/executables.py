from __future__ import annotations

import sys
from pathlib import Path


def resolve_repo_python_exe(repo_root: Path) -> str:
    """Return the repo-local virtualenv Python executable when present."""
    candidates = (
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable
