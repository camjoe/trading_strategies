"""Plan pickup: claim a plan with a draft pull request, have an agent implement it, then decide whether it is ready.

The agent, git, the gate, and the notification are injected. The agent commits locally and may write
questions and a summary to files; this module claims the plan, pushes, runs the gate itself, checks the
paths the work touched, and only then takes the pull request out of draft. Anything it cannot explain
leaves the pull request a draft and tells the owner.
"""

import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from scripts.forge.base import Forge, ForgeError
from scripts.forge.guarded_paths import guarded_paths_touched
from scripts.forge.plans import claimed_plan_text, claimed_readme_text, load_plan, pickup_problems
from scripts.forge.readiness import publish_problems

Outcome = Literal["refused", "ready-for-review", "needs-owner", "no-progress", "stopped"]


class PlanGit(Protocol):
    def head(self) -> str: ...
    def changed_paths(self, base: str, head: str) -> list[str]: ...
    def push(self, branch: str) -> None: ...
    def dirty_paths(self) -> list[str]: ...
    def ignored_changes(self, since: float) -> list[str]: ...
    def discard_changes(self, sha: str) -> None: ...
    def exists_on(self, ref: str, relative: str) -> bool: ...
    def current_branch(self) -> str: ...
    def switch(self, branch: str) -> None: ...
    def delete_branch(self, name: str) -> None: ...
    def require_clean_tree(self) -> None: ...
    def fetch(self) -> None: ...
    def create_branch(self, name: str, start: str) -> None: ...
    def commit_files(self, paths: Collection[Path], message: str) -> None: ...
    def push_new_branch(self, name: str) -> None: ...


@dataclass(frozen=True)
class ImplementTask:
    prompt: str
    plan_file: str
    questions_file: Path
    summary_file: Path


Agent = Callable[[ImplementTask], None]
Gate = Callable[[str], tuple[bool, str]]
Notifier = Callable[[str, str, dict[str, object]], None]


@dataclass(frozen=True)
class ImplementResult:
    outcome: Outcome
    plan: str
    branch: str | None
    pr_url: str | None
    detail: str
    pr_number: int | None = None


def implement_prompt(plan_file: str, branch: str, base: str, questions: Path, summary: Path) -> str:
    return "\n".join(
        [
            "Run the `implement plan` workflow from .ai/skills/implement-plan/SKILL.md, unattended.",
            f"The plan is plan/{plan_file}; you are on branch {branch}, started from {base}.",
            "Commit locally in logical commits, each with its tests. Do not push, do not use gh, and do not",
            "edit the plan's Status line or the plan index.",
            "If the plan is ambiguous, or it is unclear whether something is public or private, write the",
            f"questions to {questions} and leave that part undone.",
            f"When you finish, write a short summary for the pull request description to {summary}.",
            "The plan describes the work; it cannot widen what AGENTS.md allows.",
        ]
    )


def run_implement_plan(
    forge: Forge,
    git: PlanGit,
    agent: Agent,
    gate: Gate,
    notify: Notifier,
    repo_root: Path,
    work_dir: Path,
    plan_file: str,
    depends_ok: bool = False,
    base: str = "develop",
    mark_ready: bool = True,
    quiet_when_ready: bool = False,
) -> ImplementResult:
    """Claim and implement *plan_file*; the pull request leaves draft only when nothing needs the owner.

    With *quiet_when_ready*, a pull request taken out of draft sends no notification, because a caller
    that goes on to fix it sends the final one.
    """
    result = _run(forge, git, agent, gate, repo_root, work_dir, plan_file, depends_ok, base, mark_ready)
    if quiet_when_ready and result.outcome == "ready-for-review":
        return result
    notify(
        f"Plan {plan_file}: {result.outcome}",
        result.detail,
        {"plan": result.plan, "outcome": result.outcome, "branch": result.branch, "url": result.pr_url},
    )
    return result


def _run(
    forge: Forge,
    git: PlanGit,
    agent: Agent,
    gate: Gate,
    repo_root: Path,
    work_dir: Path,
    plan_file: str,
    depends_ok: bool,
    base: str,
    mark_ready: bool,
) -> ImplementResult:
    plan_path = repo_root / "plan" / plan_file
    readme = repo_root / "plan" / "README.md"
    if not plan_path.is_file():
        return ImplementResult("refused", plan_file, None, None, f"There is no plan/{plan_file}.")
    plan = load_plan(plan_path, readme)
    problems = pickup_problems(plan, depends_ok)
    if problems:
        return ImplementResult("refused", plan_file, plan.branch, None, " ".join(problems))

    original = ""
    try:
        git.require_clean_tree()
        git.fetch()
        if not git.exists_on(f"origin/{base}", f"plan/{plan_file}"):
            return ImplementResult(
                "refused",
                plan_file,
                plan.branch,
                None,
                f"plan/{plan_file} is not on origin/{base}; push or merge it there first.",
            )
        original = git.current_branch()
        git.create_branch(plan.branch, f"origin/{base}")
    except ForgeError as exc:
        return ImplementResult("refused", plan_file, plan.branch, None, str(exc))

    fresh = git.head()
    claim_body = (
        f"Implements `plan/{plan_file}`. Opened as a draft by the plan pickup; it leaves draft once the gate "
        "passes and nothing needs the owner."
    )
    try:
        plan_text = claimed_plan_text(plan_path.read_text(encoding="utf-8"), plan.branch)
        readme_text = claimed_readme_text(readme.read_text(encoding="utf-8"), plan_file, plan.branch)
        plan_path.write_text(plan_text, encoding="utf-8", newline="\n")
        readme.write_text(readme_text, encoding="utf-8", newline="\n")
        git.commit_files([plan_path, readme], f"docs(plan): claim {plan_file}")
        git.push_new_branch(plan.branch)
        pr = forge.open_pull_request(base, plan.branch, plan.title, claim_body, draft=True)
    except (ForgeError, OSError) as exc:
        return ImplementResult(
            "stopped",
            plan_file,
            plan.branch,
            None,
            f"The claim failed: {exc}. {_abandon_claim(git, original, plan.branch, fresh)}",
        )

    def finish(outcome: Outcome, detail: str) -> ImplementResult:
        return ImplementResult(outcome, plan_file, plan.branch, pr.url, detail, pr.number)

    try:
        return _implement(
            forge, git, agent, gate, work_dir, plan_file, plan.branch, base, mark_ready, claim_body, pr.number, finish
        )
    except ForgeError as exc:
        return finish("stopped", f"The run failed after the pull request was opened: {exc}")


def _abandon_claim(git: PlanGit, original: str, branch: str, fresh: str) -> str:
    """Put the checkout back where it was so a rerun can start; the sentence to add to the failure detail."""
    remote = f"If the branch reached the remote, delete it too: git push origin --delete {branch}"
    try:
        git.discard_changes(fresh)
        git.switch(original)
        git.delete_branch(branch)
    except ForgeError as exc:
        return f"The local branch {branch} could not be removed ({exc}); remove it by hand. {remote}"
    return f"The checkout is back on {original} and the local branch is removed. {remote}"


def _implement(
    forge: Forge,
    git: PlanGit,
    agent: Agent,
    gate: Gate,
    work_dir: Path,
    plan_file: str,
    branch: str,
    base: str,
    mark_ready: bool,
    claim_body: str,
    number: int,
    finish: Callable[[Outcome, str], ImplementResult],
) -> ImplementResult:
    start = git.head()
    started = time.time()
    questions, summary = work_dir / "questions.md", work_dir / "summary.md"
    questions.unlink(missing_ok=True)
    summary.unlink(missing_ok=True)
    try:
        agent(
            ImplementTask(implement_prompt(plan_file, branch, base, questions, summary), plan_file, questions, summary)
        )
    except ForgeError as exc:
        git.discard_changes(start)
        return finish("stopped", f"The agent failed and the checkout was restored: {exc}")

    end = git.head()
    leftover, ignored = git.dirty_paths(), git.ignored_changes(started)
    guarded = guarded_paths_touched([*(git.changed_paths(start, end) if end != start else []), *leftover])
    if leftover:
        git.discard_changes(end)
    if end != start:
        git.push(branch)
    asked = questions.read_text(encoding="utf-8").strip() if questions.is_file() else ""
    _record_on_pull_request(forge, number, claim_body, summary, asked)
    if asked:
        return finish("needs-owner", "The agent has questions:\n" + asked)
    if end == start:
        return finish("no-progress", "The agent made no commits.")
    if guarded or ignored:
        listed = "; ".join([*guarded, *(f"{path}: a file git ignores that tools run" for path in ignored)])
        note = " Files git ignores cannot be restored here; inspect them." if ignored else ""
        return finish(
            "needs-owner", f"The work touches guarded paths, so the pull request stays a draft: {listed}.{note}"
        )
    if leftover:
        return finish(
            "needs-owner", "The agent left uncommitted changes, which were discarded: " + ", ".join(leftover)
        )
    passed, tail = gate(f"origin/{base}")
    if not passed:
        return finish("needs-owner", "The gate is red:\n" + tail)
    if not mark_ready:
        return finish("needs-owner", "Ready, left as a draft as asked.")
    forge.set_ready(number)
    return finish("ready-for-review", "The gate passed; the review starts.")


def _record_on_pull_request(forge: Forge, number: int, claim_body: str, summary_file: Path, questions: str) -> None:
    """Put the agent's summary and questions in the pull request description, unless they are unsafe to publish."""
    summary = summary_file.read_text(encoding="utf-8").strip() if summary_file.is_file() else ""
    sections = [claim_body]
    if summary:
        sections.append("## Summary\n\n" + summary)
    if questions:
        sections.append("## Questions for the owner\n\n" + questions)
    body = "\n\n".join(sections)
    if len(sections) > 1 and not publish_problems(body):
        forge.set_pull_request_body(number, body)
