"""The real git, agent, and email behind the fixer loop, all running on the owner's machine."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from common.git import changed_paths, get_repo_root, git_output
from scripts.forge.base import ForgeError
from scripts.forge.fix_loop import RoundTask
from trading.interfaces.runtime.jobs.job_helpers import resolve_email_config_from_env
from trading.interfaces.runtime.notifications import notify_runtime_event

AGENT_TIMEOUT_SECONDS = 3600
_ALLOWED_TOOLS = (
    "Read,Glob,Grep,Edit,Write,Skill,Agent,"
    "Bash(git add:*),Bash(git commit:*),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),"
    "Bash(python:*),Bash(.venv/bin/python:*),Bash(.venv/Scripts/python.exe:*),Bash(.venv/bin/pytest:*),Bash(.venv/Scripts/pytest.exe:*),Bash(cat:*),Bash(ls:*)"
)
_DENIED_TOOLS = "Bash(git push:*),Bash(git reset:*),Bash(gh:*)"


class LocalGit:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or get_repo_root()

    def head(self) -> str:
        return git_output(self._root, "rev-parse", "HEAD").strip()

    def changed_paths(self, base: str, head: str) -> list[str]:
        return changed_paths(self._root, base, head)

    def reset_hard(self, sha: str) -> None:
        git_output(self._root, "reset", "--hard", sha)

    def push(self) -> None:
        git_output(self._root, "push")

    def require_clean_tree(self) -> None:
        if git_output(self._root, "status", "--porcelain").strip():
            raise ForgeError("The working tree has uncommitted changes; commit or stash them first.")


def run_claude_agent(task: RoundTask, model: str | None = None) -> None:
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
