"""A throwaway clone of the repository, with its own virtual environment, for an agent to work in.

The agent never touches the owner's checkout: it commits in the clone, and the controller fetches those
commits afterwards and checks them. Nothing else crosses back, so hooks, git configuration, ignored files,
and the virtual environment the agent changed are discarded with the clone. The clone's remote points at
nothing, so it cannot push anywhere. This isolates the repository, not the machine: code the agent writes and
runs still runs as the owner.
"""

import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scripts.forge.base import ForgeError


@dataclass(frozen=True)
class Sandbox:
    path: Path

    def uncommitted(self) -> list[str]:
        """Changed or new files git would list, ignored files excluded; commits are all that cross back."""
        try:
            completed = run_bounded(["git", "status", "--porcelain", "--untracked-files=all"], self.path)
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
) -> "subprocess.CompletedProcess[str]":
    """Run *args* and capture its output; on a timeout kill the whole process tree, then raise ``TimeoutExpired``.

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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **group,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
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
