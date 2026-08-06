"""Best-effort git command execution against a checkout.

Callers here treat git as optional: the repository may not be a checkout, git may
not be installed, or the command may simply fail. Every helper returns ``None``
in those cases rather than raising, so a caller degrades to "unknown" instead of
taking down whatever asked.
"""

from __future__ import annotations

import subprocess


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
