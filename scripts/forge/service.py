"""Forge-neutral operations built on the :class:`scripts.forge.base.Forge` interface."""

import time
from collections.abc import Callable, Collection
from dataclasses import asdict
from typing import Any

from scripts.forge.base import READINESS_MARKER, CiStatus, Forge, ForgeError


def resolve_authors(forge: Forge, authors: Collection[str]) -> tuple[str, ...]:
    """The accounts whose marker comment is trusted: *authors*, or the authenticated user when none given.

    The comment body is later read by an agent, so a marker comment from anyone else must be ignored.
    """
    if authors:
        return tuple(authors)
    try:
        return (forge.current_user(),)
    except ForgeError as exc:
        raise ForgeError(f"No trusted comment author: pass --author. ({exc})") from exc


def wait_for_ci(
    forge: Forge,
    sha: str,
    exclude: Collection[str] = (),
    timeout_seconds: float = 0,
    interval_seconds: float = 20,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> CiStatus:
    """CI status for *sha*, polling while checks are pending until *timeout_seconds* have passed."""
    deadline = clock() + timeout_seconds
    status = forge.ci_status(sha, exclude)
    while status.state == "pending" and clock() < deadline:
        sleep(interval_seconds)
        status = forge.ci_status(sha, exclude)
    return status


def review_context(
    forge: Forge,
    number: int | None,
    authors: Collection[str],
    exclude_checks: Collection[str] = (),
    wait_seconds: float = 0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Everything a readiness pass needs about a pull request, in one answer.

    ``previous_comment`` is the prior readiness comment from a trusted author, or ``None`` on a first
    pass. CI is judged for the pull request's head commit.
    """
    pr = forge.pull_request(number)
    trusted = resolve_authors(forge, authors)
    previous = forge.find_comment(pr.number, READINESS_MARKER, trusted)
    ci = wait_for_ci(forge, pr.head_sha, exclude_checks, wait_seconds, sleep=sleep, clock=clock)
    return {
        "pull_request": {**asdict(pr), "diff_base_ref": pr.diff_base_ref},
        "previous_comment": None if previous is None else asdict(previous),
        "ci": asdict(ci),
    }
