"""Run the pull-request gate and the Claude agent in containers instead of on the owner's machine.

Both containers see the clean clone mounted at ``/work``, have a read-only root filesystem, no capabilities,
no host environment variables, and memory, CPU, and process limits. The gate has no network and no credentials.
The agent has an open network and one credential, ``CLAUDE_CODE_OAUTH_TOKEN``, which code it runs can read. The images are built from the controller's own checkout so the
clone cannot change what they install. The Docker client is injected as a ``Runner`` so the controllers stay
testable without Docker.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from common.git import get_repo_root
from scripts.forge.base import ForgeError
from scripts.forge.local import AGENT_TIMEOUT_SECONDS, ALLOWED_TOOLS, DENIED_TOOLS, report_agent_result
from scripts.forge.sandbox import run_bounded


class Runner(Protocol):
    def __call__(
        self, args: list[str], timeout: float, input_text: str | None = None
    ) -> "subprocess.CompletedProcess[str]": ...


class HasFiles(Protocol):
    @property
    def prompt(self) -> str: ...

    @property
    def cwd(self) -> Path: ...

    @property
    def files(self) -> Sequence[Path]: ...


DOCKERFILE = Path("docker/gate/Dockerfile")
AGENT_DOCKERFILE = Path("docker/agent/Dockerfile")
IMAGE_REPOSITORY = "trading-gate"
AGENT_IMAGE_REPOSITORY = "trading-agent"
CLAUDE_CODE_VERSION = "2.1.296"
CLAUDE_AUTH_VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"
BUILD_TIMEOUT_SECONDS = 1800
GATE_TIMEOUT_SECONDS = 3600
WORKDIR = "/work"
EXCHANGE = "/exchange"
MEMORY = "4g"
CPUS = "4"
PIDS_LIMIT = "512"
NON_ROOT_UID = 10001
_REQUIREMENTS = ("requirements-base.txt", "requirements-dev.txt")
_EDITABLE_INSTALL = "-e ."


def docker_runner(
    args: list[str], timeout: float, input_text: str | None = None
) -> "subprocess.CompletedProcess[str]":
    """Run a Docker client command, killing it if it outlives *timeout*."""
    return run_bounded(args, Path.cwd(), timeout, input_text=input_text)


def _context_files(root: Path) -> dict[str, bytes]:
    """The gate image's build context: the Dockerfile and the requirements, without the editable install.

    ``-e .`` needs the source tree, which the image does not hold; the gate puts the clone's source on
    ``PYTHONPATH`` instead.
    """
    files = {"Dockerfile": (root / DOCKERFILE).read_bytes()}
    for name in _REQUIREMENTS:
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if line.strip() != _EDITABLE_INSTALL]
        files[name] = ("\n".join(kept) + "\n").encode("utf-8")
    return files


def _digest(parts: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(parts.items()):
        digest.update(name.encode("utf-8") + b"\0" + content + b"\0")
    return digest.hexdigest()[:12]


def image_tag(root: Path) -> str:
    """A tag that changes whenever the Dockerfile or the requirements do."""
    return f"{IMAGE_REPOSITORY}:{_digest(_context_files(root))}"


def agent_image_tag(root: Path) -> str:
    """A tag that changes with the agent Dockerfile, the gate image it builds on, or the pinned Claude version."""
    parts = {
        "Dockerfile": (root / AGENT_DOCKERFILE).read_bytes(),
        "base": image_tag(root).encode("utf-8"),
        "version": CLAUDE_CODE_VERSION.encode("utf-8"),
    }
    return f"{AGENT_IMAGE_REPOSITORY}:{_digest(parts)}"


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


def _build_if_missing(
    runner: Runner, tag: str, files: Mapping[str, bytes], build_args: Mapping[str, str], what: str
) -> None:
    if _docker(runner, ["image", "inspect", tag], 120).returncode == 0:
        return
    with tempfile.TemporaryDirectory(prefix="forge-image-") as context:
        for name, content in files.items():
            (Path(context) / name).write_bytes(content)
        arguments = ["build", "--quiet", "--tag", tag]
        for key, value in build_args.items():
            arguments += ["--build-arg", f"{key}={value}"]
        built = _docker(runner, [*arguments, context], BUILD_TIMEOUT_SECONDS)
    if built.returncode != 0:
        raise ForgeError(f"The {what} image could not be built: {_last_line(built)}")


def ensure_image(root: Path, runner: Runner = docker_runner) -> str:
    """The tag of the gate image for *root*'s requirements, building it when it is not there yet."""
    tag = image_tag(root)
    _build_if_missing(runner, tag, _context_files(root), {}, "gate")
    return tag


def ensure_agent_image(root: Path, runner: Runner = docker_runner) -> str:
    """The tag of the agent image (the gate image plus Node and the pinned Claude CLI), built when missing."""
    base = ensure_image(root, runner)
    tag = agent_image_tag(root)
    files = {"Dockerfile": (root / AGENT_DOCKERFILE).read_bytes()}
    _build_if_missing(runner, tag, files, {"BASE": base, "CLAUDE_CODE_VERSION": CLAUDE_CODE_VERSION}, "agent")
    return tag


def _user() -> str:
    """The user the container runs as: the owner's id on POSIX, where the mount keeps its host ownership."""
    if sys.platform == "win32":
        return f"{NON_ROOT_UID}:{NON_ROOT_UID}"
    return f"{os.getuid()}:{os.getgid()}"


def _isolation(name: str, clone: Path) -> list[str]:
    """The flags both containers share: no capabilities, read-only root, limits, and only the clone mounted."""
    return [
        "--rm",
        "--init",
        "--name",
        name,
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
    ]


def _environment(variables: Mapping[str, str]) -> list[str]:
    return [arg for key, value in variables.items() for arg in ("--env", f"{key}={value}")]


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
        "--network",
        "none",
        *_isolation(name, clone),
        *_environment(environment),
        image,
        "python",
        "-m",
        "scripts.run_checks",
        "pr",
        "--base",
        base,
    ]


def agent_command(
    image: str,
    name: str,
    clone: Path,
    exchange: Path,
    identity: tuple[str, str] | None,
    model: str | None,
) -> list[str]:
    """The ``docker run`` arguments for one agent session; the prompt goes in on stdin.

    The token is passed by name, so its value is never on a command line. Git reads no configuration but the
    ``safe.directory`` entry, may use only the ``file`` transport, and has no remote to push to.
    """
    environment = {
        "PATH": f"{WORKDIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "VIRTUAL_ENV": f"{WORKDIR}/.venv",
        "PYTHONPATH": f"{WORKDIR}/src:{WORKDIR}/apps",
        "LANG": "C.UTF-8",
        "HOME": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": WORKDIR,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "file",
    }
    if identity:
        author, email = identity
        environment |= {
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": author,
            "GIT_COMMITTER_EMAIL": email,
        }
    return [
        "run",
        "-i",
        *_isolation(name, clone),
        "--mount",
        f"type=bind,source={exchange},target={EXCHANGE}",
        *_environment(environment),
        "--env",
        CLAUDE_AUTH_VARIABLE,
        image,
        "-p",
        "--output-format",
        "json",
        "--allowedTools",
        ALLOWED_TOOLS,
        "--disallowedTools",
        DENIED_TOOLS,
        *(["--model", model] if model else []),
    ]


def _kill_container(runner: Runner, name: str) -> None:
    """Stop the container by name: killing the Docker client leaves the container running."""
    try:
        runner(["docker", "kill", name], 60)
    except OSError, subprocess.TimeoutExpired:
        pass


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


def _exchange_directory(files: Sequence[Path]) -> Path:
    parents = {file.parent for file in files}
    if len(parents) != 1:
        raise ForgeError("The agent's files are not in one directory, so they cannot be mounted.")
    return parents.pop()


def run_agent(
    task: HasFiles,
    model: str | None = None,
    runner: Runner = docker_runner,
    root: Path | None = None,
    identity: tuple[str, str] | None = None,
    environ: Mapping[str, str] = os.environ,
) -> None:
    """Run one agent session in a container with the sandbox at ``/work``, the way ``run_claude_agent`` does.

    The files the prompt names live outside the sandbox, so their directory is mounted at ``/exchange`` and the
    prompt's paths are rewritten to match. The token must be in *environ*; it is redacted from the output.
    """
    token = environ.get(CLAUDE_AUTH_VARIABLE, "")
    if not token:
        raise ForgeError(
            f"{CLAUDE_AUTH_VARIABLE} is not set. Set it in this shell to a token from `claude setup-token`; "
            "code the agent runs can read it."
        )
    image = ensure_agent_image(root or get_repo_root(), runner)
    prompt = task.prompt
    for file in task.files:
        prompt = prompt.replace(str(file), f"{EXCHANGE}/{file.name}")
    name = f"forge-agent-{uuid.uuid4().hex[:12]}"
    command = agent_command(image, name, task.cwd, _exchange_directory(task.files), identity, model)
    try:
        completed = runner(["docker", *command], AGENT_TIMEOUT_SECONDS, prompt)
    except FileNotFoundError as exc:
        raise ForgeError("The container agent needs Docker, which could not be started.") from exc
    except subprocess.TimeoutExpired as exc:
        _kill_container(runner, name)
        raise ForgeError("The agent timed out.") from exc
    report_agent_result(
        subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            completed.stdout.replace(token, "<token>"),
            completed.stderr.replace(token, "<token>"),
        )
    )
