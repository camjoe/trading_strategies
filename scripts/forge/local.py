"""The real git, agent, and email behind the fixer loop, all running on the owner's machine."""

import json
import subprocess
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any, Protocol

from common.git import get_repo_root, git_output, split_nul, uncommitted_paths
from scripts.forge.base import ForgeError
from trading.interfaces.runtime.jobs.job_helpers import resolve_email_config_from_env
from trading.interfaces.runtime.notifications import notify_runtime_event

AGENT_TIMEOUT_SECONDS = 3600
_PYTHONS = ("python", ".venv/bin/python", ".venv/Scripts/python.exe")
_PYTHON_MODULES = (
    "scripts.run_checks",
    "scripts.fix_checks",
    "scripts.checks.run_suite",
    "scripts.forge check-body",
    "pytest",
)
_ALLOWED_TOOLS = ",".join(
    [
        "Read",
        "Glob",
        "Grep",
        "Edit",
        "Write",
        "Skill",
        "Agent",
        *(f"Bash(git {verb}:*)" for verb in ("add", "commit", "status", "diff", "log", "show")),
        "Bash(.venv/bin/pytest:*)",
        "Bash(.venv/Scripts/pytest.exe:*)",
        "Bash(ls:*)",
        *(f"Bash({python} -m {module}:*)" for python in _PYTHONS for module in _PYTHON_MODULES),
    ]
)
_DENIED_TOOLS = ",".join(
    [
        *(f"Bash(git {verb}:*)" for verb in ("push", "reset", "clean", "config", "update-ref", "checkout", "restore")),
        "Bash(gh:*)",
        "Edit(.git/**)",
        "Write(.git/**)",
    ]
)


class HasPrompt(Protocol):
    @property
    def prompt(self) -> str: ...


class LocalGit:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or get_repo_root()

    def head(self) -> str:
        return git_output(self._root, "rev-parse", "HEAD").strip()

    def changed_paths(self, base: str, head: str) -> list[str]:
        """Every path changed from *base* to *head*, with renames reported as a delete and an add."""
        return split_nul(git_output(self._root, "diff", "--name-only", "--no-renames", "-z", f"{base}..{head}"))

    def dirty_paths(self) -> list[str]:
        """Tracked files with uncommitted changes and untracked files that git does not ignore."""
        return uncommitted_paths(self._root)

    def discard_changes(self, sha: str) -> None:
        """Return the checkout to *sha*, dropping later commits, edits, and untracked files."""
        git_output(self._root, "reset", "--hard", sha)
        git_output(self._root, "clean", "-fd")

    def push(self, branch: str) -> None:
        """Push HEAD to the remote branch named *branch*, whatever the upstream setting says."""
        try:
            git_output(self._root, "push", "origin", f"HEAD:refs/heads/{branch}")
        except subprocess.CalledProcessError as exc:
            raise ForgeError(f"git push to {branch} failed: {(exc.stderr or '').strip()}") from exc

    def fetch(self) -> None:
        git_output(self._root, "fetch", "origin")

    def create_branch(self, name: str, start: str) -> None:
        try:
            git_output(self._root, "switch", "-c", name, start)
        except subprocess.CalledProcessError as exc:
            raise ForgeError(f"Could not create branch {name} from {start}: {(exc.stderr or '').strip()}") from exc

    def commit_files(self, paths: Collection[Path], message: str) -> None:
        git_output(self._root, "add", *(str(path) for path in paths))
        git_output(self._root, "commit", "-m", message)

    def remove_and_commit(self, remove: Collection[Path], update: Collection[Path], message: str) -> None:
        git_output(self._root, "rm", "-q", *(str(path) for path in remove))
        git_output(self._root, "add", *(str(path) for path in update))
        git_output(self._root, "commit", "-m", message)

    def push_new_branch(self, name: str) -> None:
        git_output(self._root, "push", "-u", "origin", name)

    def require_clean_tree(self) -> None:
        if git_output(self._root, "status", "--porcelain").strip():
            raise ForgeError("The working tree has uncommitted changes; commit or stash them first.")


def run_claude_agent(task: HasPrompt, model: str | None = None) -> None:
    """Run one fixer round with the headless ``claude`` CLI, signed in as the owner."""
    model_args = ["--model", model] if model else []
    try:
        completed = subprocess.run(
            [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--allowedTools",
                _ALLOWED_TOOLS,
                "--disallowedTools",
                _DENIED_TOOLS,
                *model_args,
            ],
            input=task.prompt,
            text=True,
            encoding="utf-8",
            cwd=get_repo_root(),
            capture_output=True,
            timeout=AGENT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ForgeError("The claude CLI is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ForgeError("The fixer agent timed out.") from exc
    result = _agent_result(completed.stdout)
    if completed.returncode != 0 or result.get("is_error"):
        raise ForgeError(f"The fixer agent failed: {result.get('result') or completed.stderr.strip() or 'no output'}")
    denials = result.get("permission_denials") or []
    print(
        f"Fixer agent: {result.get('num_turns')} turns, {result.get('duration_ms')} ms, "
        f"{len(denials)} permission denials.",
        file=sys.stderr,
    )
    for denial in denials:
        command = (denial.get("tool_input") or {}).get("command") or denial.get("tool_name")
        print(f"  denied: {str(command)[:120]}", file=sys.stderr)


def _agent_result(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def email_notifier(subject: str, message: str, details: dict[str, object]) -> None:
    """Email the owner through the runtime alert settings; a missing configuration sends nothing."""
    config = resolve_email_config_from_env()
    delivered = notify_runtime_event(
        event="pr-readiness-loop",
        status="ok" if details.get("outcome") == "ready" else "warn",
        message=f"{subject}. {message}",
        details=details,
        email_config=config,
    )
    if not delivered:
        reason = "the SMTP settings are not set" if config is None else "delivery failed"
        print(f"No email was sent: {reason}.", file=sys.stderr)


def run_gate(base: str) -> tuple[bool, str]:
    """Run the pull-request gate against *base*; return whether it passed and the end of its output."""
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.run_checks", "pr", "--base", base],
        cwd=get_repo_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = "\n".join((completed.stdout + completed.stderr).strip().splitlines()[-15:])
    return completed.returncode == 0, tail
