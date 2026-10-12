"""Run the pull-request gate in a container instead of on the owner's machine.

The container sees one directory, the clean clone, mounted at ``/work``; it has no network, a read-only root
filesystem, no capabilities, no host environment variables, and memory, CPU, and process limits. The image
holds Python and the dev requirements, built from the controller's own checkout so the clone cannot change
what the image installs. The Docker client is injected as a ``Runner`` so the controllers stay testable
without Docker.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from common.git import get_repo_root
from scripts.forge.base import ForgeError
from scripts.forge.sandbox import run_bounded

Runner = Callable[[list[str], float], "subprocess.CompletedProcess[str]"]

DOCKERFILE = Path("docker/gate/Dockerfile")
IMAGE_REPOSITORY = "trading-gate"
BUILD_TIMEOUT_SECONDS = 1800
GATE_TIMEOUT_SECONDS = 3600
WORKDIR = "/work"
MEMORY = "4g"
CPUS = "4"
PIDS_LIMIT = "512"
NON_ROOT_UID = 10001
_REQUIREMENTS = ("requirements-base.txt", "requirements-dev.txt")
_EDITABLE_INSTALL = "-e ."


def docker_runner(args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    """Run a Docker client command, killing it if it outlives *timeout*."""
    return run_bounded(args, Path.cwd(), timeout)


def _context_files(root: Path) -> dict[str, bytes]:
    """The build context: the Dockerfile and the requirements, without the editable install of the workspace.

    ``-e .`` needs the source tree, which the image does not hold; the gate puts the clone's source on
    ``PYTHONPATH`` instead.
    """
    files = {"Dockerfile": (root / DOCKERFILE).read_bytes()}
    for name in _REQUIREMENTS:
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if line.strip() != _EDITABLE_INSTALL]
        files[name] = ("\n".join(kept) + "\n").encode("utf-8")
    return files


def image_tag(root: Path) -> str:
    """A tag that changes whenever the Dockerfile or the requirements do."""
    digest = hashlib.sha256()
    for name, content in sorted(_context_files(root).items()):
        digest.update(name.encode("utf-8") + b"\0" + content + b"\0")
    return f"{IMAGE_REPOSITORY}:{digest.hexdigest()[:12]}"


def _last_line(completed: "subprocess.CompletedProcess[str]") -> str:
    lines = (completed.stderr or completed.stdout or "").strip().splitlines()
    return lines[-1] if lines else f"exit status {completed.returncode}"


def _docker(runner: Runner, args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    try:
        return runner(["docker", *args], timeout)
    except FileNotFoundError as exc:
        raise ForgeError("The container gate needs Docker, which could not be started.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ForgeError(f"Docker step timed out ({args[0]}).") from exc


def ensure_image(root: Path, runner: Runner = docker_runner) -> str:
    """The tag of the gate image for *root*'s requirements, building it when it is not there yet."""
    tag = image_tag(root)
    if _docker(runner, ["image", "inspect", tag], 120).returncode == 0:
        return tag
    with tempfile.TemporaryDirectory(prefix="gate-image-") as context:
        for name, content in _context_files(root).items():
            (Path(context) / name).write_bytes(content)
        built = _docker(runner, ["build", "--quiet", "--tag", tag, context], BUILD_TIMEOUT_SECONDS)
    if built.returncode != 0:
        raise ForgeError(f"The gate image could not be built: {_last_line(built)}")
    return tag


def _user() -> str:
    """The user the gate runs as: the owner's id on POSIX, where the mount keeps its host ownership."""
    if sys.platform == "win32":
        return f"{NON_ROOT_UID}:{NON_ROOT_UID}"
    return f"{os.getuid()}:{os.getgid()}"


def gate_command(image: str, name: str, clone: Path, base: str) -> list[str]:
    """The ``docker run`` arguments for the gate: everything the container may see or do is listed here."""
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": f"{WORKDIR}/src:{WORKDIR}/apps",
        "LANG": "C.UTF-8",
        "HOME": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return [
        "run",
        "--rm",
        "--init",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=512m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        _user(),
        "--memory",
        MEMORY,
        "--cpus",
        CPUS,
        "--pids-limit",
        PIDS_LIMIT,
        "--mount",
        f"type=bind,source={clone},target={WORKDIR}",
        "--workdir",
        WORKDIR,
        *(arg for key, value in environment.items() for arg in ("--env", f"{key}={value}")),
        image,
        "python",
        "-m",
        "scripts.run_checks",
        "pr",
        "--base",
        base,
    ]


def run_gate(
    base: str,
    cwd: Path,
    runner: Runner = docker_runner,
    root: Path | None = None,
) -> tuple[bool, str]:
    """Run the pull-request gate against *base* for the clone at *cwd* inside a container.

    Returns whether it passed and the tail of its output. Frontend checks are not run: the image has no Node.
    """
    image = ensure_image(root or get_repo_root(), runner)
    name = f"forge-gate-{uuid.uuid4().hex[:12]}"
    try:
        completed = runner(["docker", *gate_command(image, name, cwd, base)], GATE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_container(runner, name)
        return False, "The gate timed out."
    tail = "\n".join((completed.stdout + completed.stderr).strip().splitlines()[-15:])
    return completed.returncode == 0, tail


def _kill_container(runner: Runner, name: str) -> None:
    """Stop the container by name: killing the Docker client leaves the container running."""
    try:
        runner(["docker", "kill", name], 60)
    except OSError, subprocess.TimeoutExpired:
        pass
