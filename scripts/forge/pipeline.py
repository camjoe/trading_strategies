"""Plan pickup followed by the fixer loop: implement a plan, wait for the first review, then fix until READY.

The pickup takes the pull request out of draft; the review workflow then posts its first readiness
comment; the fixer loop has nothing to work from until it does. This module is only the join between
the two controllers, so a run that starts with the owner's command ends with one notification.
"""

import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scripts.forge.base import Forge, ForgeError
from scripts.forge.fix_loop import Agent as FixAgent, LoopResult, run_fix_loop, wait_for_next_pass
from scripts.forge.implement import (
    Agent as ImplementAgent,
    Gate,
    ImplementResult,
    Notifier,
    PlanGit,
    run_implement_plan,
)
from scripts.forge.sandbox import SandboxFactory
from scripts.forge.service import resolve_authors


class PipelineGit(PlanGit, Protocol):
    """What both controllers need from git."""


@dataclass(frozen=True)
class PipelineResult:
    implement: ImplementResult
    fix: LoopResult | None
    detail: str


def run_pipeline(
    forge: Forge,
    git: PipelineGit,
    implement_agent: ImplementAgent,
    fix_agent: FixAgent,
    sandbox: SandboxFactory,
    gate: Gate,
    notify: Notifier,
    repo_root: Path,
    work_dir: Path,
    plan_file: str,
    authors: Collection[str],
    depends_ok: bool = False,
    base: str = "develop",
    mark_ready: bool = True,
    fix: bool = True,
    max_rounds: int = 3,
    review_wait_seconds: float = 1800,
    wait_seconds: float = 2700,
    interval_seconds: float = 30,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> PipelineResult:
    """Implement *plan_file*; when its pull request leaves draft, carry on into the fixer loop."""
    chaining = fix and mark_ready
    implemented = run_implement_plan(
        forge, git, implement_agent, sandbox, gate, notify, repo_root, work_dir, plan_file, depends_ok, base, mark_ready,
        quiet_when_ready=chaining,
    )  # fmt: skip
    if not chaining or implemented.outcome != "ready-for-review" or implemented.pr_number is None:
        return PipelineResult(implemented, None, implemented.detail)

    number = implemented.pr_number
    stopped = _stop_before_fixing(forge, git, authors, number, review_wait_seconds, interval_seconds, sleep, clock)
    if stopped is not None:
        notify(
            f"Plan {plan_file}: fixer not started",
            stopped,
            {"plan": plan_file, "outcome": "stopped", "branch": implemented.branch, "url": implemented.pr_url},
        )
        return PipelineResult(implemented, None, stopped)

    fixed = run_fix_loop(
        forge, git, fix_agent, sandbox, notify, work_dir, number, authors, max_rounds, wait_seconds, interval_seconds,
        repo_root, sleep, clock,
    )  # fmt: skip
    return PipelineResult(implemented, fixed, fixed.detail)


def _stop_before_fixing(
    forge: Forge,
    git: PipelineGit,
    authors: Collection[str],
    number: int,
    review_wait_seconds: float,
    interval_seconds: float,
    sleep: Callable[[float], None] | None,
    clock: Callable[[], float] | None,
) -> str | None:
    """Why the fixer cannot start yet, or ``None`` when the first review has arrived and the tree is clean."""
    try:
        git.require_clean_tree()
        trusted = resolve_authors(forge, authors)
    except ForgeError as exc:
        return f"The pull request is ready, but the fixer did not start: {exc}"
    first = wait_for_next_pass(
        forge,
        number,
        trusted,
        None,
        review_wait_seconds,
        interval_seconds,
        sleep or time.sleep,
        clock or time.monotonic,
    )
    if first is None:
        return "The pull request is ready, but its first review did not arrive in time; run fix-loop once it does."
    return None
