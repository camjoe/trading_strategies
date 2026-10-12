"""The real git, agent, and email behind the fixer loop, all running on the owner's machine."""

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, Protocol

from common.git import get_repo_root, git_output, split_nul
from scripts.forge.base import ForgeError
from scripts.forge.sandbox import run_bounded, venv_python

AGENT_TIMEOUT_SECONDS = 3600
_CONTROLLER_GIT = ("-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false")
GATE_TIMEOUT_SECONDS = 3600
_PYTHONS = ("python", ".venv/bin/python", ".venv/Scripts/python.exe")
_PYTHON_MODULES = (
    "scripts.run_checks",
    "scripts.fix_checks",
    "scripts.checks.run_suite",
    "scripts.forge check-body",
    "pytest",
)
ALLOWED_TOOLS = ",".join(
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
DENIED_TOOLS = ",".join(
    [
        *(f"Bash(git {verb}:*)" for verb in ("push", "reset", "clean", "config", "update-ref", "checkout", "restore")),
        "Bash(gh:*)",
        "Edit(.git/**)",
        "Write(.git/**)",
    ]
)

_SECRET_NAME = re.compile(
    r"TOKEN|SECRET|PASSW|API_?KEY|CREDENTIAL|WEBHOOK|SMTP|^TRADING_RUNTIME|^SSH_AUTH_SOCK$", re.IGNORECASE
)
_KEPT_FOR_CLAUDE = ("CLAUDE", "ANTHROPIC")


class HasPrompt(Protocol):
    @property
    def prompt(self) -> str: ...

    @property
    def cwd(self) -> Path: ...


class LocalGit:
    """Git in the owner's checkout, run with hooks and ``fsmonitor`` off."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or get_repo_root()

    def _run(self, *args: str) -> str:
        return git_output(self._root, *_CONTROLLER_GIT, *args)

    def _git(self, *args: str) -> str:
        try:
            return self._run(*args)
        except subprocess.CalledProcessError as exc:
            raise ForgeError(f"git {args[0]} failed: {(exc.stderr or '').strip()}") from exc

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def identity(self) -> tuple[str, str] | None:
        """The configured commit author name and email, or ``None`` when either is missing."""
        try:
            name, email = self._git("config", "user.name").strip(), self._git("config", "user.email").strip()
        except ForgeError:
            return None
        return (name, email) if name and email else None

    def changed_paths(self, base: str, head: str) -> list[str]:
        """Every path changed from *base* to *head*, with renames reported as a delete and an add."""
        return split_nul(self._git("diff", "--name-only", "--no-renames", "-z", f"{base}..{head}"))

    def current_branch(self) -> str:
        return self._git("branch", "--show-current").strip()

    def switch(self, branch: str) -> None:
        self._git("switch", branch)

    def delete_branch(self, name: str) -> None:
        self._git("branch", "-D", name)

    def import_commits(self, source: Path, since: str) -> str:
        """Fetch HEAD of the repository at *source* and return its commit; nothing is checked out.

        Refused unless that commit is *since* or descends from it, so the commits are an honest range to check.
        """
        self._git("fetch", "--no-tags", "--quiet", str(source), "HEAD")
        sha = self._git("rev-parse", "FETCH_HEAD^{commit}").strip()
        try:
            self._run("merge-base", "--is-ancestor", since, sha)
        except subprocess.CalledProcessError as exc:
            if exc.returncode != 1:
                raise ForgeError(f"git merge-base failed: {(exc.stderr or '').strip()}") from exc
            raise ForgeError(
                f"The sandbox's commits do not descend from {since[:12]}; they were not imported."
            ) from exc
        return sha

    def hold(self, name: str, sha: str) -> str:
        """Keep *sha* under a local-only ref for the owner to inspect; returns the ref. Nothing is pushed."""
        ref = f"refs/forge/held/{name}/{sha[:12]}"
        self._git("update-ref", ref, sha)
        return ref

    def fast_forward(self, sha: str) -> None:
        """Move the current branch to *sha*, which must descend from it."""
        self._git("merge", "--ff-only", "--quiet", sha)

    def show(self, ref: str, relative: str) -> str:
        """The text of *relative* as it is at *ref*."""
        return self._git("show", f"{ref}:{relative}")

    def exists_on(self, ref: str, relative: str) -> bool:
        """Whether *relative* exists in the tree at *ref*."""
        try:
            self._run("cat-file", "-e", f"{ref}:{relative}")
        except subprocess.CalledProcessError:
            return False
        return True

    def discard_changes(self, sha: str) -> None:
        """Return the checkout to *sha*, dropping later commits, edits, and untracked files."""
        self._git("reset", "--hard", sha)
        self._git("clean", "-fd")

    def push(self, branch: str) -> None:
        """Push HEAD to the remote branch named *branch*, whatever the upstream setting says."""
        try:
            self._run("push", "origin", f"HEAD:refs/heads/{branch}")
        except subprocess.CalledProcessError as exc:
            raise ForgeError(f"git push to {branch} failed: {(exc.stderr or '').strip()}") from exc

    def fetch(self) -> None:
        self._git("fetch", "origin")

    def create_branch(self, name: str, start: str) -> None:
        try:
            self._run("switch", "-c", name, start)
        except subprocess.CalledProcessError as exc:
            raise ForgeError(f"Could not create branch {name} from {start}: {(exc.stderr or '').strip()}") from exc

    def commit_files(self, paths: Collection[Path], message: str, remove: Collection[Path] = ()) -> None:
        """Commit *paths* (added or updated) and the deletion of *remove* in one commit."""
        if remove:
            self._git("rm", "-q", *(str(path) for path in remove))
        self._git("add", *(str(path) for path in paths))
        self._git("commit", "-m", message)

    def require_clean_tree(self) -> None:
        if self._git("status", "--porcelain").strip():
            raise ForgeError("The working tree has uncommitted changes; commit or stash them first.")


def agent_environment(
    base: Mapping[str, str], scratch: Path, identity: tuple[str, str] | None = None, workdir: Path | None = None
) -> dict[str, str]:
    """The environment the agent runs in: the owner's, minus anything that could push or call GitHub.

    Secret-looking variables go (except Claude's own), git reads an empty configuration with no credential
    helper and may only use the ``file`` transport, and ``gh`` reads an empty configuration directory.
    Commits still work: the owner's name and email are passed as the author and committer. With *workdir*,
    the virtual environment in it comes first on ``PATH`` and is the active one, so a ``pip install`` lands there.
    """
    env = {
        name: value
        for name, value in base.items()
        if name.startswith(_KEPT_FOR_CLAUDE) or not _SECRET_NAME.search(name)
    }
    empty_gitconfig = scratch / "gitconfig"
    empty_gitconfig.write_text("", encoding="utf-8")
    gh_config = scratch / "gh"
    gh_config.mkdir(exist_ok=True)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(empty_gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "file",
            "GH_CONFIG_DIR": str(gh_config),
        }
    )
    if workdir is not None:
        venv = workdir / ".venv"
        env.pop("PYTHONHOME", None)
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = os.pathsep.join([str(venv_python(venv).parent), env.get("PATH", "")])
    if identity:
        name, email = identity
        env.update(
            {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
            }
        )
    return env


def run_claude_agent(task: HasPrompt, model: str | None = None) -> None:
    """Run one agent session with the headless ``claude`` CLI, signed in as the owner."""
    model_args = ["--model", model] if model else []
    root = get_repo_root()
    try:
        with tempfile.TemporaryDirectory(prefix="agent-env-") as scratch:
            completed = subprocess.run(
                [
                    "claude",
                    "-p",
                    "--output-format",
                    "json",
                    "--allowedTools",
                    ALLOWED_TOOLS,
                    "--disallowedTools",
                    DENIED_TOOLS,
                    *model_args,
                ],
                input=task.prompt,
                text=True,
                encoding="utf-8",
                cwd=task.cwd,
                env=agent_environment(os.environ, Path(scratch), LocalGit(root).identity(), task.cwd),
                capture_output=True,
                timeout=AGENT_TIMEOUT_SECONDS,
            )
    except FileNotFoundError as exc:
        raise ForgeError("The claude CLI is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ForgeError("The agent timed out.") from exc
    report_agent_result(completed)


def report_agent_result(completed: "subprocess.CompletedProcess[str]") -> None:
    """Raise ``ForgeError`` if the finished ``claude -p`` run failed; otherwise print a one-line summary."""
    result = _agent_result(completed.stdout)
    if completed.returncode != 0 or result.get("is_error"):
        raise ForgeError(f"The agent failed: {result.get('result') or completed.stderr.strip() or 'no output'}")
    denials = result.get("permission_denials") or []
    print(
        f"Agent: {result.get('num_turns')} turns, {result.get('duration_ms')} ms, {len(denials)} permission denials.",
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
    """Email the owner through the runtime alert settings; a missing configuration sends nothing.

    Do not import ``trading`` at module level in this file: the workflow's posting job imports it.
    """
    try:
        from trading.interfaces.runtime.jobs.job_helpers import resolve_email_config_from_env
        from trading.interfaces.runtime.notifications import notify_runtime_event

        config = resolve_email_config_from_env()
        delivered = notify_runtime_event(
            event="pr-readiness-loop",
            status="ok" if details.get("outcome") == "ready" else "warn",
            message=f"{subject}. {message}",
            details=details,
            email_config=config,
        )
    except OSError as exc:
        print(f"No email was sent: {type(exc).__name__} while sending.", file=sys.stderr)
        return
    if not delivered:
        reason = "the SMTP settings are not set" if config is None else "delivery failed"
        print(f"No email was sent: {reason}.", file=sys.stderr)


def run_gate(base: str, cwd: Path) -> tuple[bool, str]:
    """Run the pull-request gate against *base* in the checkout at *cwd*, with the interpreter running this command.

    The checkout is expected to be a clean clone without a virtual environment of its own; its source comes
    first on ``PYTHONPATH``. It runs with the agent's scrubbed environment. The interpreter needs the dev
    requirements installed.
    """
    with tempfile.TemporaryDirectory(prefix="gate-env-") as scratch:
        env = agent_environment(os.environ, Path(scratch))
        env["PYTHONPATH"] = os.pathsep.join([str(cwd / "src"), str(cwd / "apps")])
        return _run_gate(base, cwd, env)


def _run_gate(base: str, cwd: Path, env: dict[str, str]) -> tuple[bool, str]:
    try:
        completed = run_bounded(
            [sys.executable, "-m", "scripts.run_checks", "pr", "--base", base],
            cwd,
            GATE_TIMEOUT_SECONDS,
            env,
        )
    except subprocess.TimeoutExpired:
        return False, "The gate timed out."
    tail = "\n".join((completed.stdout + completed.stderr).strip().splitlines()[-15:])
    return completed.returncode == 0, tail
