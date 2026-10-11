"""Forge-neutral types and the interface every code-hosting adapter implements.

A forge is the platform that hosts the repository and its pull requests (GitHub, GitLab, ...).
Callers depend on :class:`Forge`; only an adapter module knows which platform it talks to.
"""

from collections.abc import Collection
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

READINESS_MARKER = "<!-- pr-readiness -->"

CiState = Literal["pass", "fail", "pending", "none"]


class ForgeError(RuntimeError):
    """A forge operation failed or was refused."""


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
