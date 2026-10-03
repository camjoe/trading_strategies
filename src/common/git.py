"""Best-effort git interrogation of the current checkout.

Everything here asks git a question about the repository the code is running
from: where its root is, what revision is checked out, or an arbitrary command.

All of it is best-effort by design. The repository may not be a checkout, git
may not be installed, or a command may simply fail — so these degrade to
``None`` rather than raising, with the exception of :func:`get_repo_root`, whose
callers cannot proceed without an answer.

No domain dependencies; usable from any layer.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path


def run_git(*args: str, cwd: str) -> str | None:
    """Run ``git -C cwd <args>`` and return stripped stdout, or ``None`` on failure.

    ``None`` covers both a non-zero exit and empty output — callers only ever want
    a usable value or nothing.
    """
    completed = subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


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


@lru_cache(maxsize=1)
def git_head_revision() -> str | None:
    """Return the current git HEAD commit SHA, or ``None`` if it cannot be resolved.

    Used to stamp provenance on audit records (e.g. an optimizer run manifest) so
    they say which build produced them. Cached: the revision is fixed for a
    process's lifetime.
    """
    try:
        repo_root = get_repo_root(Path(__file__))
    except RuntimeError:
        return None

    return run_git("rev-parse", "HEAD", cwd=str(repo_root))
