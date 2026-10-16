"""Plan pickup: claim a plan with a draft pull request, have an agent implement it, then decide whether it is ready.

The agent, git, the gate, and the notification are injected. The agent commits locally and may write
questions and a summary to files; this module claims the plan, pushes, runs the gate itself, checks the
paths the work touched, and only then takes the pull request out of draft. Anything it cannot explain
leaves the pull request a draft and tells the owner.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from scripts.forge.base import CheckoutGit, Forge, ForgeError
from scripts.forge.guarded_paths import guarded_paths_touched
from scripts.forge.plans import claimed_plan_text, claimed_readme_text, parse_plan, pickup_problems
from scripts.forge.readiness import commits_hold_ambient_secret, publish_problems
from scripts.forge.sandbox import SandboxFactory, leftover_message, read_agent_text
from scripts.forge.tools import RESTRICTED_SHELL

Outcome = Literal["refused", "ready-for-review", "needs-owner", "no-progress", "stopped"]


class PlanGit(CheckoutGit, Protocol):
    """The checkout operations the pickup uses, beyond the ones it shares with the fixer loop."""

    def exists_on(self, ref: str, relative: str) -> bool: ...
    def show(self, ref: str, relative: str) -> str: ...
    def current_branch(self) -> str: ...
    def switch(self, branch: str) -> None: ...
    def delete_branch(self, name: str) -> None: ...
    def require_clean_tree(self) -> None: ...
    def fetch(self) -> None: ...
    def create_branch(self, name: str, start: str) -> None: ...
    def hold(self, name: str, sha: str) -> str: ...


@dataclass(frozen=True)
class ImplementTask:
    prompt: str
    questions_file: Path
    summary_file: Path
    cwd: Path

    @property
    def files(self) -> tuple[Path, ...]:
        """Files outside the sandbox that the prompt names, for an agent that cannot see the host's paths."""
        return (self.questions_file, self.summary_file)


Agent = Callable[[ImplementTask], None]
Gate = Callable[[str, Path], tuple[bool, str]]
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
            f"The plan is plan/{plan_file}; your commits will be pushed to branch {branch}, started from {base}.",
            "You are in a throwaway clone of the repository with its own .venv, on a detached HEAD: commit on it",
            "and do not create or switch branches. Commit in logical commits, each with its tests, and leave no",
            "uncommitted changes. Run `git add` and `git commit` as separate commands, never chained with `&&`.",
            RESTRICTED_SHELL,
            "Do not push or use gh, and do not edit the plan's Status line or the plan index.",
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
    sandbox: SandboxFactory,
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

    With *quiet_when_ready*, a pull request taken out of draft sends no notification; the caller sends the
    final one.
    """
    result = _run(forge, git, agent, sandbox, gate, repo_root, work_dir, plan_file, depends_ok, base, mark_ready)
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
    sandbox: SandboxFactory,
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
    base_ref = f"origin/{base}"
    original = ""
    branch_name: str | None = None
    try:
        git.require_clean_tree()
        git.fetch()
        if not git.exists_on(base_ref, f"plan/{plan_file}"):
            return ImplementResult(
                "refused",
                plan_file,
                None,
                None,
                f"plan/{plan_file} is not on {base_ref}; push or merge it there first.",
            )
        plan = parse_plan(plan_file, git.show(base_ref, f"plan/{plan_file}"), git.show(base_ref, "plan/README.md"))
        branch_name = plan.branch
        problems = pickup_problems(plan, depends_ok)
        if problems:
            return ImplementResult("refused", plan_file, plan.branch, None, " ".join(problems))
        original = git.current_branch()
        if not original:
            return ImplementResult(
                "refused",
                plan_file,
                plan.branch,
                None,
                "The checkout is on a detached HEAD; switch to a branch first.",
            )
        git.create_branch(plan.branch, base_ref)
        fresh = git.head()
    except ForgeError as exc:
        return ImplementResult("refused", plan_file, branch_name, None, str(exc))

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
        git.push(plan.branch)
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
            forge,
            git,
            agent,
            sandbox,
            gate,
            work_dir,
            plan_file,
            plan.branch,
            base,
            mark_ready,
            claim_body,
            pr.number,
            finish,
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
    sandbox: SandboxFactory,
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
    """Run the agent in a sandbox, import its commits, and decide whether the pull request may leave draft.

    The agent works in a throwaway clone; the owner's checkout is untouched until its commits have been
    fetched. The gate runs in a second, clean clone of the pushed commit.
    """
    start = git.head()
    questions, summary = work_dir / "questions.md", work_dir / "summary.md"
    questions.unlink(missing_ok=True)
    summary.unlink(missing_ok=True)
    with sandbox(start) as box:
        task = ImplementTask(
            implement_prompt(plan_file, branch, base, questions, summary), questions, summary, box.path
        )
        try:
            agent(task)
        except ForgeError as exc:
            return finish("stopped", f"The agent failed: {exc}")
        end = git.import_commits(box.path, start)
        leftover = box.uncommitted()
    committed = end != start
    changed = git.changed_paths(start, end)
    guarded = guarded_paths_touched(changed)
    leaked = commits_hold_ambient_secret(git, changed, start, end)
    try:
        asked = read_agent_text(questions).strip()
        summary_text = read_agent_text(summary).strip()
        unreadable = ""
    except ForgeError as exc:
        asked = summary_text = ""
        unreadable = str(exc)
    held_note = ""
    if committed and (guarded or leaked or unreadable):
        try:
            held = git.hold(branch, end)
            held_note = f" Nothing was pushed; the commits are kept in {held} in your repository, for you to inspect."
        except ForgeError as exc:
            held_note = (
                f" Nothing was pushed, and the commits could not be kept under a ref ({exc}). They are in your "
                f"repository as commit {end}, unreferenced: run git branch <name> {end} to keep them."
            )
    elif committed:
        git.fast_forward(end)
        git.push(branch)
    note = _record_on_pull_request(forge, number, claim_body, summary_text, asked) + held_note

    def done(outcome: Outcome, detail: str) -> ImplementResult:
        return finish(outcome, detail + note)

    if unreadable:
        return done(
            "needs-owner",
            f"{unreadable} Nothing was published, and the pull request stays a draft.",
        )
    if asked:
        return done("needs-owner", "The agent has questions:\n" + asked)
    if not committed:
        return done("no-progress", "The agent made no commits.")
    if guarded:
        return done(
            "needs-owner",
            "The work touches guarded paths, so it was not pushed and the pull request stays a draft: "
            + "; ".join(guarded),
        )
    if leaked:
        return done(
            "needs-owner",
            "The commits contain the Claude token, so they were not pushed and the pull request stays a draft.",
        )
    if leftover:
        return done(
            "needs-owner",
            leftover_message("The agent", "which were not pushed, so the pull request stays a draft", leftover),
        )
    with sandbox(end, install=False) as clean:
        passed, tail = gate(f"origin/{base}", clean.path)
    if not passed:
        return done("needs-owner", "The gate is red:\n" + tail)
    if not mark_ready:
        return done("needs-owner", "Ready, left as a draft as asked.")
    forge.set_ready(number)
    return done("ready-for-review", "The gate passed; the review starts.")


def _record_on_pull_request(forge: Forge, number: int, claim_body: str, summary: str, questions: str) -> str:
    """Put the agent's summary and questions in the pull request description, unless they are unsafe to publish.

    Returns a sentence for the result detail when the text was withheld, otherwise an empty string.
    """
    sections = [claim_body]
    if summary:
        sections.append("## Summary\n\n" + summary)
    if questions:
        sections.append("## Questions for the owner\n\n" + questions)
    body = "\n\n".join(sections)
    if len(sections) == 1:
        return ""
    if publish_problems(body):
        return " The agent's summary or questions were withheld from the description as unsafe to publish."
    forge.set_pull_request_body(number, body)
    return ""
