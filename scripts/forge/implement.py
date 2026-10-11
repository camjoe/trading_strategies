"""Plan pickup: claim a plan with a draft pull request, have an agent implement it, then decide whether it is ready.

The agent, git, the gate, and the notification are injected. The agent commits locally and may write
questions and a summary to files; this module claims the plan, pushes, runs the gate itself, checks the
paths the work touched, and only then takes the pull request out of draft. Anything it cannot explain
leaves the pull request a draft and tells the owner.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from scripts.forge.base import Forge, ForgeError
from scripts.forge.guarded_paths import guarded_paths_touched
from scripts.forge.plans import claimed_plan_text, claimed_readme_text, load_plan, pickup_problems
from scripts.forge.readiness import leak_problems

Outcome = Literal["refused", "ready-for-review", "needs-owner", "no-progress", "stopped"]


class PlanGit(Protocol):
    def head(self) -> str: ...
    def changed_paths(self, base: str, head: str) -> list[str]: ...
    def push(self) -> None: ...
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
) -> ImplementResult:
    """Claim and implement *plan_file*; the pull request leaves draft only when nothing needs the owner."""
    result = _run(forge, git, agent, gate, repo_root, work_dir, plan_file, depends_ok, base, mark_ready)
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

    try:
        git.require_clean_tree()
        git.fetch()
        git.create_branch(plan.branch, f"origin/{base}")
    except ForgeError as exc:
        return ImplementResult("refused", plan_file, plan.branch, None, str(exc))

    plan_text = claimed_plan_text(plan_path.read_text(encoding="utf-8"), plan.branch)
    readme_text = claimed_readme_text(readme.read_text(encoding="utf-8"), plan_file, plan.branch)
    plan_path.write_text(plan_text, encoding="utf-8", newline="\n")
    readme.write_text(readme_text, encoding="utf-8", newline="\n")
    git.commit_files([plan_path, readme], f"docs(plan): claim {plan_file}")
    git.push_new_branch(plan.branch)
    claim_body = (
        f"Implements `plan/{plan_file}`. Opened as a draft by the plan pickup; it leaves draft once the gate "
        "passes and nothing needs the owner."
    )
    pr = forge.open_pull_request(base, plan.branch, plan.title, claim_body, draft=True)

    start = git.head()
    questions, summary = work_dir / "questions.md", work_dir / "summary.md"
    questions.unlink(missing_ok=True)
    summary.unlink(missing_ok=True)
    try:
        agent(
            ImplementTask(
                implement_prompt(plan_file, plan.branch, base, questions, summary), plan_file, questions, summary
            )
        )
    except ForgeError as exc:
        return ImplementResult("stopped", plan_file, plan.branch, pr.url, f"The agent failed: {exc}")

    end = git.head()
    committed = end != start
    if committed:
        git.push()
    asked = questions.read_text(encoding="utf-8").strip() if questions.is_file() else ""
    _record_on_pull_request(forge, pr.number, claim_body, summary, asked)
    if asked:
        return ImplementResult("needs-owner", plan_file, plan.branch, pr.url, "The agent has questions:\n" + asked)
    if not committed:
        return ImplementResult("no-progress", plan_file, plan.branch, pr.url, "The agent made no commits.")
    guarded = guarded_paths_touched(git.changed_paths(start, end))
    if guarded:
        return ImplementResult(
            "needs-owner", plan_file, plan.branch, pr.url, "The work touches guarded paths: " + "; ".join(guarded)
        )
    passed, tail = gate(f"origin/{base}")
    if not passed:
        return ImplementResult("needs-owner", plan_file, plan.branch, pr.url, "The gate is red:\n" + tail)
    if not mark_ready:
        return ImplementResult("needs-owner", plan_file, plan.branch, pr.url, "Ready, left as a draft as asked.")
    forge.set_ready(pr.number)
    return ImplementResult("ready-for-review", plan_file, plan.branch, pr.url, "The gate passed; the review starts.")


def _record_on_pull_request(forge: Forge, number: int, claim_body: str, summary_file: Path, questions: str) -> None:
    """Put the agent's summary and questions in the pull request description, unless they are unsafe to publish."""
    summary = summary_file.read_text(encoding="utf-8").strip() if summary_file.is_file() else ""
    sections = [claim_body]
    if summary:
        sections.append("## Summary\n\n" + summary)
    if questions:
        sections.append("## Questions for the owner\n\n" + questions)
    body = "\n\n".join(sections)
    if len(sections) > 1 and not leak_problems(body):
        forge.set_pull_request_body(number, body)
