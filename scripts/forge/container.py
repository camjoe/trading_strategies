"""Run the pull-request gate and the Claude agent in Docker containers.

Both containers mount the clean clone at ``/work`` with a read-only root, no capabilities, resource limits, and
only the environment variables set here. The gate has no network and no credentials. The agent has an open
network and ``CLAUDE_CODE_OAUTH_TOKEN``, which code it runs can read. The images are built from the controller's
own checkout. The Docker client is injected as a ``Runner`` so tests need no Docker.
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
    """Runs a Docker client command with a timeout and optional stdin; raises ``TimeoutExpired`` when it overruns."""

    def __call__(
        self, args: list[str], timeout: float, input_text: str | None = None
    ) -> "subprocess.CompletedProcess[str]": ...


class HasFiles(Protocol):
    """An agent task: its prompt, the sandbox it works in, and the files outside it that the prompt names."""

    @property
    def prompt(self) -> str: ...

    @property
    def cwd(self) -> Path: ...

    @property
    def files(self) -> Sequence[Path]: ...


DOCKERFILE = Path("docker/Dockerfile")
IMAGE_REPOSITORY = "trading-gate"
AGENT_IMAGE_REPOSITORY = "trading-agent"
CLAUDE_CODE_VERSION = "2.1.296"
PERMISSION_MODE = "dontAsk"
PERMISSION_PROMPTS = "none"
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
    """A tag that changes with the Dockerfile, the requirements, or the pinned Claude version."""
    parts = {**_context_files(root), "version": CLAUDE_CODE_VERSION.encode("utf-8")}
    return f"{AGENT_IMAGE_REPOSITORY}:{_digest(parts)}"


def _last_line(completed: "subprocess.CompletedProcess[str]") -> str:
    lines = (completed.stderr or completed.stdout or "").strip().splitlines()
    return lines[-1] if lines else f"exit status {completed.returncode}"


def _docker(runner: Runner, args: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    try:
        return runner(["docker", *args], timeout)
    except FileNotFoundError as exc:
        raise ForgeError(
            "Docker could not be started, and the container runs need it: install and start Docker, "
            "or pass --no-container to run the gate on this machine."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ForgeError(f"Docker step timed out ({args[0]}).") from exc


_DAEMON_DOWN = (
    "cannot connect to the docker daemon",
    "failed to connect to the docker api",
    "error during connect",
    "is the docker daemon running",
)


def _daemon_down(completed: "subprocess.CompletedProcess[str]") -> bool:
    text = (completed.stderr + completed.stdout).lower()
    return any(marker in text for marker in _DAEMON_DOWN)


def _build_if_missing(
    runner: Runner, tag: str, files: Mapping[str, bytes], build_args: Mapping[str, str], target: str
) -> None:
    inspected = _docker(runner, ["image", "inspect", tag], 120)
    if inspected.returncode == 0:
        return
    if _daemon_down(inspected):
        raise ForgeError(
            "Docker is installed but its daemon is not running: start Docker, "
            "or pass --no-container to run the gate on this machine."
        )
    with tempfile.TemporaryDirectory(prefix="forge-image-") as context:
        for name, content in files.items():
            (Path(context) / name).write_bytes(content)
        arguments = ["build", "--quiet", "--tag", tag, "--target", target]
        for key, value in build_args.items():
            arguments += ["--build-arg", f"{key}={value}"]
        built = _docker(runner, [*arguments, context], BUILD_TIMEOUT_SECONDS)
    if built.returncode != 0:
        raise ForgeError(f"The {target} image could not be built: {_last_line(built)}")


def ensure_image(root: Path, runner: Runner = docker_runner) -> str:
    """The tag of the gate image for *root*'s requirements, building it when it is not there yet."""
    tag = image_tag(root)
    _build_if_missing(runner, tag, _context_files(root), {}, "gate")
    return tag


def ensure_agent_image(root: Path, runner: Runner = docker_runner) -> str:
    """The tag of the agent image (the Dockerfile's agent stage: the gate plus Node and the pinned Claude CLI)."""
    tag = agent_image_tag(root)
    _build_if_missing(runner, tag, _context_files(root), {"CLAUDE_CODE_VERSION": CLAUDE_CODE_VERSION}, "agent")
    return tag


def _user() -> str:
    """The user the container runs as: the owner's id on POSIX, where the mount keeps its host ownership."""
    if sys.platform == "win32":
        return f"{NON_ROOT_UID}:{NON_ROOT_UID}"
    return f"{os.getuid()}:{os.getgid()}"


def _mount(source: Path, target: str) -> list[str]:
    """A bind mount of *source* at *target*; a comma in the path would add mount options, so it is refused."""
    if "," in str(source):
        raise ForgeError(f"A path with a comma cannot be mounted safely: {source}")
    return ["--mount", f"type=bind,source={source},target={target}"]


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
        *_mount(clone, WORKDIR),
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
    ``safe.directory`` entry, may use only the ``file`` transport, and has no remote to push to. Anything not
    in the allow list is denied, not prompted for.
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
        *_mount(exchange, EXCHANGE),
        *_environment(environment),
        "--env",
        CLAUDE_AUTH_VARIABLE,
        image,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        PERMISSION_MODE,
        "--permission-prompts",
        PERMISSION_PROMPTS,
        "--strict-mcp-config",
        "--allowedTools",
        ALLOWED_TOOLS,
        "--disallowedTools",
        DENIED_TOOLS,
        *(["--model", model] if model else []),
    ]


def _kill_container(runner: Runner, name: str) -> None:
    """Stop the container by name, since killing the Docker client leaves it running; say so when that fails."""
    try:
        completed = runner(["docker", "kill", name], 60)
        already_gone = "No such container" in completed.stderr or "is not running" in completed.stderr
        stopped = completed.returncode == 0 or already_gone
    except OSError, subprocess.TimeoutExpired:
        stopped = False
    if not stopped:
        print(f"The container {name} may still be running; stop it with: docker rm -f {name}", file=sys.stderr)


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


def _missing_token_message() -> str:
    return (
        f"{CLAUDE_AUTH_VARIABLE} is not set. Set it in this shell to a token from `claude setup-token`; "
        "code the agent runs can read it."
    )


def preflight(
    root: Path,
    *,
    gate: bool,
    agent: bool,
    runner: Runner = docker_runner,
    environ: Mapping[str, str] = os.environ,
) -> None:
    """Fail before a plan is claimed when a container run could not start.

    That is Docker not running, an image that cannot be built, or, for the agent, a missing token.
    """
    if agent and not environ.get(CLAUDE_AUTH_VARIABLE):
        raise ForgeError(_missing_token_message())
    if gate:
        ensure_image(root, runner)
    if agent:
        ensure_agent_image(root, runner)


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
        raise ForgeError(_missing_token_message())
    image = ensure_agent_image(root or get_repo_root(), runner)
    prompt = task.prompt
    for file in task.files:
        prompt = prompt.replace(str(file), f"{EXCHANGE}/{file.name}")
    name = f"forge-agent-{uuid.uuid4().hex[:12]}"
    command = agent_command(image, name, task.cwd, _exchange_directory(task.files), identity, model)
    try:
        completed = runner(["docker", *command], AGENT_TIMEOUT_SECONDS, prompt)
    except FileNotFoundError as exc:
        raise ForgeError(
            "Docker could not be started, and the container agent needs it: install and start Docker, "
            "or run without --agent-container."
        ) from exc
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
