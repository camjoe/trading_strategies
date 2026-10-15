"""A throwaway clone of the repository, with its own virtual environment, for an agent to work in.

The agent never touches the owner's checkout: it commits in the clone, and the controller fetches those
commits afterwards and checks them. Nothing else crosses back, so ignored files and the virtual environment
the agent changed are discarded with the clone. The clone's remote points at nothing, so it cannot push
anywhere. The agent can write the clone's ``.git`` directory, so ``harden_clone`` resets what git would run
from it before the controller runs git there. This isolates the repository, not the machine: code the agent
writes and runs still runs as the owner, unless it ran in a container.
"""

import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scripts.forge.base import CheckoutGit, ForgeError
from scripts.forge.readiness import contains_ambient_secret

NO_EXEC_GIT = ("-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false")
SECRET_NAME = re.compile(
    r"TOKEN|SECRET|PASSW|API_?KEY|CREDENTIAL|WEBHOOK|SMTP|^TRADING_RUNTIME|^SSH_AUTH_SOCK$", re.IGNORECASE
)
TRUSTED_CONFIG = "trusted-git-config"
_UNTRUSTED_GIT_PATHS = ("hooks", "objects/info/alternates", "info/attributes", "commondir", "config.worktree")


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, onexc=_make_writable)


def harden_clone(path: Path) -> None:
    """Reset what git would run from the clone at *path*, which an agent or a container may have written.

    ``.git`` must be a plain directory. Its configuration is replaced by the copy saved when the sandbox was
    built (when there is one), and hooks, alternates, attributes, and worktree redirection are removed, so a
    configured ``core.fsmonitor`` or filter command cannot run when the controller uses git there. Anything
    that cannot be cleaned raises ``ForgeError``.
    """
    git_dir = path / ".git"
    try:
        if git_dir.is_symlink() or not git_dir.is_dir():
            raise ForgeError("The sandbox's .git is not a plain directory, so git was not run there.")
        for relative in _UNTRUSTED_GIT_PATHS:
            _remove(git_dir / relative)
        trusted = path.parent / TRUSTED_CONFIG
        if trusted.is_file():
            _remove(git_dir / "config")
            shutil.copyfile(trusted, git_dir / "config")
    except OSError as exc:
        raise ForgeError(f"The sandbox's .git could not be cleaned, so git was not run there: {exc}") from exc


def scrubbed(base: Mapping[str, str], keep_prefixes: tuple[str, ...] = ()) -> dict[str, str]:
    """*base* without secret-looking variables, except those whose name starts with one of *keep_prefixes*."""
    return {
        name: value for name, value in base.items() if name.startswith(keep_prefixes) or not SECRET_NAME.search(name)
    }


def commits_hold_ambient_secret(git: CheckoutGit, paths: Sequence[str], start: str, end: str) -> bool:
    """Whether the commits from *start* to *end*, their changed *paths* included, hold a secret from this environment."""
    return end != start and contains_ambient_secret("\n".join([*paths, git.outgoing_text(start, end)]))


def git_environment() -> dict[str, str]:
    """This process's environment without secret-looking variables."""
    return scrubbed(os.environ)


@dataclass(frozen=True)
class Sandbox:
    path: Path

    def uncommitted(self) -> list[str]:
        """Changed or new files git would list, ignored files excluded; commits are all that cross back."""
        harden_clone(self.path)
        try:
            completed = run_bounded(
                ["git", *NO_EXEC_GIT, "status", "--porcelain", "--untracked-files=all"],
                self.path,
                env=git_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ForgeError("Sandbox step timed out (git status).") from exc
        if completed.returncode != 0:
            raise ForgeError(f"Sandbox step failed (git status): {completed.stderr.strip()}")
        return [line for line in completed.stdout.splitlines() if line.strip()]


class SandboxFactory(Protocol):
    def __call__(self, ref: str, install: bool = True) -> AbstractContextManager[Sandbox]: ...


STEP_TIMEOUT_SECONDS = 900


def venv_python(venv: Path) -> Path:
    """The interpreter inside a virtual environment, on any platform."""
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def read_agent_text(path: Path) -> str:
    """The text of a file an agent wrote, or an empty string when it does not exist.

    A link, a directory, or any other kind of file raises ``ForgeError``: an agent that can write the file's
    directory could make a link point at a file on this machine.
    """
    try:
        info = path.lstat()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise ForgeError(f"{path.name} could not be inspected, so it was not read: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ForgeError(f"{path.name} is not a plain file, so it was not read.")
    return path.read_text(encoding="utf-8")


def leftover_message(who: str, consequence: str, lines: list[str], limit: int = 5) -> str:
    """The sentence reported when *who* left uncommitted files in a sandbox: *consequence*, then up to *limit* files."""
    return f"{who} left uncommitted changes in the sandbox, {consequence}: " + "; ".join(lines[:limit])


def _kill_tree(process: "subprocess.Popen[str]") -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)


def run_bounded(
    args: list[str],
    cwd: Path,
    timeout: float = STEP_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> "subprocess.CompletedProcess[str]":
    """Run *args*, feed it *input_text* on stdin, and capture its output.

    On a timeout kill the whole process tree, then raise ``TimeoutExpired``.

    ``subprocess.run`` kills only the direct child, and grandchildren holding the output pipes would keep
    the call from returning.
    """
    group: dict[str, Any] = (
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        if sys.platform == "win32"
        else {"start_new_session": True}
    )
    with subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **group,
    ) as process:
        try:
            stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            process.communicate()
            raise
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _run(args: list[str], cwd: Path) -> None:
    label = " ".join(args[:3])
    try:
        completed = run_bounded(args, cwd)
    except subprocess.TimeoutExpired as exc:
        raise ForgeError(f"Sandbox step timed out ({label}).") from exc
    except FileNotFoundError as exc:
        raise ForgeError(f"Sandbox step could not start: {args[0]}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()[-1:] or [
            f"exit status {completed.returncode}"
        ]
        raise ForgeError(f"Sandbox step failed ({label}): {detail[0]}")


def build_sandbox(
    root: Path, ref: str, parent: Path, identity: tuple[str, str] | None = None, install: bool = True
) -> Sandbox:
    """Clone *root* at *ref* into *parent*, cut off its remote, and (by default) install the dev requirements."""
    dest = parent / "repo"
    _run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(root), str(dest)], parent)
    _run(["git", "checkout", "--quiet", "--detach", ref], dest)
    # The checks diff against remote-tracking refs, which a clone does not copy; bring them, then cut the remote.
    _run(["git", "fetch", "--quiet", "--no-tags", str(root), "+refs/remotes/origin/*:refs/remotes/origin/*"], dest)
    _run(["git", "remote", "set-url", "origin", str(parent / "no-such-remote")], dest)
    # FETCH_HEAD and the reflogs record the source repository's path.
    (dest / ".git" / "FETCH_HEAD").unlink(missing_ok=True)
    shutil.rmtree(dest / ".git" / "logs", ignore_errors=True)
    if identity:
        _run(["git", "config", "user.name", identity[0]], dest)
        _run(["git", "config", "user.email", identity[1]], dest)
    shutil.copyfile(dest / ".git" / "config", parent / TRUSTED_CONFIG)
    if install:
        _run([sys.executable, "-m", "venv", str(dest / ".venv")], dest)
        python = venv_python(dest / ".venv")
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--quiet",
                "-r",
                "requirements-dev.txt",
            ],
            dest,
        )
    return Sandbox(dest)


def _make_writable(function: Callable[[str], object], path: str, _exc: object) -> None:
    """Remove read-only files, which git creates and Windows will not delete."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


@contextmanager
def sandbox(root: Path, ref: str, identity: tuple[str, str] | None = None, install: bool = True) -> Iterator[Sandbox]:
    """A sandbox at *ref* that is deleted when the block ends, however it ends."""
    parent = Path(tempfile.mkdtemp(prefix="forge-sandbox-"))
    try:
        yield build_sandbox(root, ref, parent, identity, install)
    finally:
        try:
            shutil.rmtree(parent, onexc=_make_writable)
        except OSError as exc:
            print(f"The sandbox at {parent} could not be deleted; remove it by hand: {exc}", file=sys.stderr)
