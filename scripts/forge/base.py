"""Forge-neutral types and the interface every code-hosting adapter implements.

A forge is the platform that hosts the repository and its pull requests (GitHub, GitLab, ...).
Callers depend on :class:`Forge`; only an adapter module knows which platform it talks to.
"""

from collections.abc import Collection
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

READINESS_MARKER = "<!-- pr-readiness -->"

RESTRICTED_SHELL = (
    "Your shell is restricted: create and edit files with the Write and Edit tools, and run only `git add`, "
    "`commit`, `rm`, `mv`, `status`, `diff`, `log`, `show`, `ls`, and the repository's pytest, `fix_checks`, "
    "`run_checks`, and `run_suite`. A refused command does not mean the shell is unusable: use a file tool or "
    "one of those commands instead, and do not write a question for it."
)

CiState = Literal["pass", "fail", "pending", "none"]


class ForgeError(RuntimeError):
    """A forge operation failed or was refused."""


def printable(text: str) -> str:
    """*text* with control, formatting, and non-printing characters shown as escapes, except newline and tab.

    Text an agent wrote is untrusted; printed raw, an escape sequence in it would act on the owner's terminal.
    """
    return "".join(
        char
        if char in "\n\t" or char.isprintable()
        else f"\\u{ord(char):04x}"
        if ord(char) < 0x10000
        else f"\\U{ord(char):08x}"
        for char in text
    )


class CheckoutGit(Protocol):
    """What the fixer loop and the plan pickup both need from git in the owner's checkout."""

    def head(self) -> str: ...
    def changed_paths(self, base: str, head: str) -> list[str]: ...
    def outgoing_text(self, base: str, head: str) -> str: ...
    def import_commits(self, source: Path, since: str) -> str: ...
    def fast_forward(self, sha: str) -> None: ...
    def discard_changes(self, sha: str) -> None: ...
    def push(self, branch: str) -> None: ...
    def commit_files(self, paths: Collection[Path], message: str, remove: Collection[Path] = ()) -> None: ...


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    base_ref: str
    head_ref: str
    head_sha: str
    is_draft: bool
    state: str

    @property
    def diff_base_ref(self) -> str:
        """The base branch as a remote ref, which exists in any checkout (a CI clone has no local base)."""
        return f"origin/{self.base_ref}"

    def to_dict(self) -> dict[str, Any]:
        """The fields plus ``diff_base_ref``, ready for JSON."""
        return {**asdict(self), "diff_base_ref": self.diff_base_ref}


@dataclass(frozen=True)
class Comment:
    id: int
    body: str
    author: str


@dataclass(frozen=True)
class CheckRun:
    name: str
    state: CiState


@dataclass(frozen=True)
class CiStatus:
    sha: str
    state: CiState
    checks: tuple[CheckRun, ...]


class Forge(Protocol):
    def current_user(self) -> str:
        """Login of the authenticated account."""
        ...

    def pull_request(self, number: int | None) -> PullRequest:
        """The pull request *number*, or the one for the current branch when ``None``."""
        ...

    def find_comment(self, number: int, authors: Collection[str]) -> Comment | None:
        """The readiness comment on *number* written by one of *authors*."""
        ...

    def upsert_comment(self, number: int, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
        """Edit the readiness comment in place, or create it. Returns the comment and whether it was created."""
        ...

    def ci_status(self, sha: str, exclude: Collection[str] = ()) -> CiStatus:
        """Aggregate state of the checks on commit *sha*, ignoring checks named in *exclude*."""
        ...

    def open_pull_request(self, base: str, head: str, title: str, body: str, draft: bool = True) -> PullRequest:
        """Open a pull request from branch *head* into *base*."""
        ...

    def set_ready(self, number: int) -> None:
        """Take pull request *number* out of draft."""
        ...

    def set_pull_request_body(self, number: int, body: str) -> None:
        """Replace the description of pull request *number*."""
        ...


def aggregate_ci_state(states: Collection[CiState]) -> CiState:
    """One state for a set of checks: any failure wins, then any pending, else pass; ``none`` when empty."""
    if not states:
        return "none"
    if "fail" in states:
        return "fail"
    if "pending" in states:
        return "pending"
    return "pass"


def require_marker(body: str) -> None:
    """Refuse a comment body that does not start with the readiness marker.

    Every write goes through this, so the tool can post only the readiness comment.
    """
    if not body.startswith(READINESS_MARKER):
        raise ForgeError(f"Comment body must start with {READINESS_MARKER!r}.")
