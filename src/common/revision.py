"""Best-effort source-revision discovery for provenance/audit records.

Reports the current git commit so an audit record (e.g. an optimizer run manifest)
can say which build produced it. Best-effort by design: returns ``None`` when git
is unavailable or the code runs outside a checkout, so a missing revision degrades
to "unknown" rather than failing the caller.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from common.git import run_git
from common.paths.repo_paths import get_repo_root


@lru_cache(maxsize=1)
def git_head_revision() -> str | None:
    """Return the current git HEAD commit SHA, or ``None`` if it cannot be resolved.

    Cached: the revision is fixed for a process's lifetime.
    """
    try:
        repo_root = get_repo_root(Path(__file__))
    except RuntimeError:
        return None

    return run_git("rev-parse", "HEAD", cwd=str(repo_root))
