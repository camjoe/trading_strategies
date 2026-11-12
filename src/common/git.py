"""Best-effort git interrogation of the current checkout.

Everything here asks git a question about the repository the code is running
from: where its root is, what revision is checked out, or an arbitrary command.

Most of it is best-effort by design. The repository may not be a checkout, git
may not be installed, or a command may simply fail — so these degrade to
``None`` rather than raising, with the exception of :func:`get_repo_root`, whose
callers cannot proceed without an answer.

The strict helpers (:func:`git_output` and the path and ref helpers built on it)
are for callers that must report a failed command: they raise
``subprocess.CalledProcessError``. Path lists are read with ``-z`` and output is
decoded as UTF-8, because git otherwise quotes non-ASCII names and the locale
decides how the bytes are read.

No domain dependencies; usable from any layer.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path


def run_git(*args: str, cwd: str) -> str | None:
    """Run ``git <args>`` in *cwd* and return stripped stdout, or ``None`` on failure.

    ``None`` covers both a non-zero exit and empty output — callers only ever want
    a usable value or nothing.
    """
    try:
        output = git_output(cwd, *args)
    except subprocess.CalledProcessError:
        return None
    return output.strip() or None


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


def git_output(repo_root: Path | str, *args: str) -> str:
    """Run ``git <args>`` in *repo_root* and return its stdout.

    Raises ``subprocess.CalledProcessError`` when git exits non-zero.
    """
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def split_nul(output: str) -> list[str]:
    """Split ``-z`` output into its non-empty entries."""
    return [entry for entry in output.split("\0") if entry]


def diff_range(base_ref: str | None, head_ref: str = "HEAD") -> list[str]:
    """Revision arguments for a diff: ``base...head`` (changes on the branch), or ``HEAD`` with no base."""
    return [f"{base_ref}...{head_ref}"] if base_ref else ["HEAD"]


def changed_paths(repo_root: Path | str, base_ref: str | None = None, head_ref: str = "HEAD") -> list[str]:
    """Paths changed by ``base...head``, or by the working tree against ``HEAD`` with no base."""
    return split_nul(git_output(repo_root, "diff", "--name-only", "-z", *diff_range(base_ref, head_ref)))


def untracked_paths(repo_root: Path | str) -> list[str]:
    """Untracked files that git does not ignore."""
    return split_nul(git_output(repo_root, "ls-files", "--others", "--exclude-standard", "-z"))


def uncommitted_paths(repo_root: Path | str) -> list[str]:
    """Tracked files with uncommitted changes, plus untracked files git does not ignore."""
    tokens = git_output(repo_root, "status", "--porcelain", "-z").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        entry = tokens[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":
            index += 1  # a rename or copy is followed by its old path
    return paths


def merge_base(repo_root: Path | str, ref: str, head_ref: str = "HEAD") -> str:
    """The abbreviated commit a ``ref...head`` diff starts from."""
    commit = git_output(repo_root, "merge-base", ref, head_ref).strip()
    return git_output(repo_root, "rev-parse", "--short", commit).strip()
