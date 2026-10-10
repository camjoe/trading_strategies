"""Forge-neutral types and the interface every code-hosting adapter implements.

A forge is the platform that hosts the repository and its pull requests (GitHub, GitLab, ...).
Callers depend on :class:`Forge`; only an adapter module knows which platform it talks to.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal, Protocol

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

    def find_comment(self, number: int, marker: str, authors: Collection[str]) -> Comment | None:
        """The comment on *number* that starts with *marker* and was written by one of *authors*."""
        ...

    def upsert_comment(self, number: int, marker: str, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
        """Edit the marker comment in place, or create it. Returns the comment and whether it was created."""
        ...

    def ci_status(self, sha: str, exclude: Collection[str] = ()) -> CiStatus:
        """Aggregate state of the checks on commit *sha*, ignoring checks named in *exclude*."""
        ...


def require_marker(body: str, marker: str) -> None:
    """Refuse a comment body that does not start with *marker*.

    Every write goes through this, so the tool can post only the marker-tagged comment.
    """
    if not body.startswith(marker):
        raise ForgeError(f"Comment body must start with {marker!r}.")
