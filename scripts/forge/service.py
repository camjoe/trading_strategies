"""Forge-neutral operations built on the :class:`scripts.forge.base.Forge` interface."""

import time
from collections.abc import Callable, Collection
from dataclasses import asdict
from typing import Any

from scripts.forge.base import CiStatus, Forge, ForgeError
from scripts.forge.readiness import pass_number

NONE_GRACE_SECONDS = 120


def resolve_authors(forge: Forge, authors: Collection[str]) -> tuple[str, ...]:
    """The accounts whose readiness comment is trusted: *authors*, or the authenticated user when none given.

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
    none_grace_seconds: float = NONE_GRACE_SECONDS,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> CiStatus:
    """CI status for *sha*, polling until it is settled or *timeout_seconds* have passed.

    Right after a push the commit has no check runs, or only the first job of a workflow, so a clean
    reading counts as settled only when a second reading, one interval later, shows the same checks.
    ``none`` is treated as still starting for the first *none_grace_seconds*. A failure is returned at
    once. With no timeout this is a single reading.
    """
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    start = clock()
    deadline = start + timeout_seconds
    status = forge.ci_status(sha, exclude)
    confirmed = None
    while status.state != "fail":
        settled = status.state == "pass" or (status.state == "none" and clock() - start >= none_grace_seconds)
        if settled and confirmed == status.checks:
            break
        if clock() >= deadline:
            break
        confirmed = status.checks if settled else None
        sleep(interval_seconds)
        status = forge.ci_status(sha, exclude)
    return status


def review_context(
    forge: Forge,
    number: int | None,
    authors: Collection[str],
    exclude_checks: Collection[str] = (),
    wait_seconds: float = 0,
    expected_sha: str | None = None,
    max_passes: int | None = None,
) -> dict[str, Any]:
    """Everything a readiness pass needs about a pull request, in one answer.

    ``previous_comment`` is the prior readiness comment from a trusted author, or ``None`` on a first
    pass; ``previous_pass`` is its pass number. CI is judged for the pull request's head commit.
    Raises when the head is not *expected_sha* (a newer push landed), or when a previous comment's
    pass number cannot be read while *max_passes* is set, so a cap never fails open.
    """
    pr = forge.pull_request(number)
    if expected_sha is not None and pr.head_sha != expected_sha:
        raise ForgeError(
            f"The pull request head is {pr.head_sha}, not the expected {expected_sha}; a newer push landed."
        )
    previous = forge.find_comment(pr.number, resolve_authors(forge, authors))
    previous_pass = None if previous is None else pass_number(previous.body)
    if max_passes is not None and previous is not None and previous_pass is None:
        raise ForgeError("Cannot read the pass number in the previous readiness comment.")
    ci = wait_for_ci(forge, pr.head_sha, exclude_checks, wait_seconds)
    return {
        "pull_request": pr.to_dict(),
        "previous_comment": None if previous is None else asdict(previous),
        "previous_pass": previous_pass,
        "pass_cap_reached": max_passes is not None and (previous_pass or 0) >= max_passes,
        "ci": asdict(ci),
    }
