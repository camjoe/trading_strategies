import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.forge import container
from scripts.forge.base import ForgeError

REPO_ROOT = Path(__file__).resolve().parents[2]
# `CLAUDE_CODE_VERSION: "2.1.296"` in the workflow's env block.
WORKFLOW_PINNED_VERSION = re.compile(r'CLAUDE_CODE_VERSION:\s*"([^"]+)"')
# The stage name in each `FROM <image> AS <stage>` line of the Dockerfile.
DOCKERFILE_STAGE = re.compile(r"^FROM .* AS (\w+)$", re.MULTILINE)


def completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["docker"], returncode, stdout, stderr)


class FakeDocker:
    """Records each Docker client call; ``image_present`` answers ``image inspect``."""

    def __init__(self, image_present: bool = True, gate: subprocess.CompletedProcess[str] | None = None) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self.inputs: list[str | None] = []
        self.image_present = image_present
        self.gate = gate or completed("ok")
        self.timeout_on_run = False
        self.built_files: dict[str, str] = {}

    def __call__(
        self, args: list[str], timeout: float, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, timeout))
        self.inputs.append(input_text)
        verb = args[1]
        if verb == "image":
            return completed(returncode=0 if self.image_present else 1)
        if verb == "build":
            context = Path(args[-1])
            self.built_files = {p.name: p.read_text(encoding="utf-8") for p in context.iterdir()}
            return completed()
        if verb == "run":
            if self.timeout_on_run:
                raise subprocess.TimeoutExpired("docker", timeout)
            return self.gate
        return completed()

    def verbs(self) -> list[str]:
        return [args[1] for args, _ in self.calls]

    def run_args(self) -> list[str]:
        return next(args for args, _ in self.calls if args[1] == "run")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = tmp_path / "owner"
    (repo / "docker").mkdir(parents=True)
    (repo / "docker" / "Dockerfile").write_text(
        "FROM python:3.14-slim AS gate\nFROM gate AS agent\nARG CLAUDE_CODE_VERSION\n", encoding="utf-8"
    )
    (repo / "requirements-base.txt").write_text("numpy==1\n", encoding="utf-8")
    (repo / "requirements-dev.txt").write_text("-r requirements-base.txt\npytest==9\n-e .\n", encoding="utf-8")
    return repo


class TestImageTag:
    def test_it_changes_with_the_requirements_and_the_dockerfile_and_not_otherwise(self, root: Path) -> None:
        first = container.image_tag(root)

        assert container.image_tag(root) == first
        (root / "requirements-base.txt").write_text("numpy==2\n", encoding="utf-8")
        second = container.image_tag(root)
        (root / "docker" / "Dockerfile").write_text("FROM python:3.15-slim AS gate\n", encoding="utf-8")
        third = container.image_tag(root)

        assert len({first, second, third}) == 3 and first.startswith("trading-gate:")

    def test_the_editable_install_does_not_affect_the_tag(self, root: Path) -> None:
        first = container.image_tag(root)
        (root / "requirements-dev.txt").write_text("-r requirements-base.txt\npytest==9\n", encoding="utf-8")

        assert container.image_tag(root) == first


class TestEnsureImage:
    def test_an_existing_image_is_reused_without_a_build(self, root: Path) -> None:
        docker = FakeDocker(image_present=True)

        tag = container.ensure_image(root, docker)

        assert tag == container.image_tag(root) and docker.verbs() == ["image"]

    def test_a_missing_image_is_built_from_the_owners_files_without_the_editable_install(self, root: Path) -> None:
        docker = FakeDocker(image_present=False)

        container.ensure_image(root, docker)

        assert docker.verbs() == ["image", "build"]
        assert set(docker.built_files) == {"Dockerfile", "requirements-base.txt", "requirements-dev.txt"}
        assert "-e ." not in docker.built_files["requirements-dev.txt"]
        assert "pytest==9" in docker.built_files["requirements-dev.txt"]

    def test_a_failed_build_stops_with_its_last_line(self, root: Path) -> None:
        calls: list[str] = []

        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(args[1])
            if args[1] == "image":
                return completed(returncode=1)
            return completed(returncode=1, stderr="step 1\nno space left")

        with pytest.raises(ForgeError, match="could not be built: no space left"):
            container.ensure_image(root, runner)

        assert calls == ["image", "build"]

    def test_a_missing_docker_client_says_so(self, root: Path) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("docker")

        with pytest.raises(ForgeError, match="Docker could not be started.*pass --no-container"):
            container.ensure_image(root, runner)


class TestGateCommand:
    def test_the_container_gets_no_network_no_writable_root_no_capabilities_and_limits(
        self, root: Path, tmp_path: Path
    ) -> None:
        docker = FakeDocker()

        container.run_gate("origin/develop", tmp_path / "clone", docker, root)

        args = docker.run_args()
        joined = " ".join(args)
        for flag in (
            "--network none",
            "--read-only",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
            f"--memory {container.MEMORY}",
            f"--cpus {container.CPUS}",
            f"--pids-limit {container.PIDS_LIMIT}",
            "--rm",
        ):
            assert flag in joined
        assert args[-6:] == ["python", "-m", "scripts.run_checks", "pr", "--base", "origin/develop"]

    def test_only_the_clone_is_mounted_and_the_environment_is_the_listed_variables(
        self, root: Path, tmp_path: Path
    ) -> None:
        docker = FakeDocker()
        clone = tmp_path / "clone"

        container.run_gate("origin/develop", clone, docker, root)

        args = docker.run_args()
        mounts = [args[i + 1] for i, arg in enumerate(args) if arg in ("--mount", "-v", "--volume")]
        assert mounts == [f"type=bind,source={clone},target=/work"]
        names = {args[i + 1].split("=", 1)[0] for i, arg in enumerate(args) if arg == "--env"}
        assert names == {"PATH", "PYTHONPATH", "LANG", "HOME", "PYTHONDONTWRITEBYTECODE"}
        assert not any(arg in ("--env-file", "--privileged", "--network=host", "--pid") for arg in args)

    def test_the_container_does_not_run_as_root(
        self, root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(container.sys, "platform", "win32")
        docker = FakeDocker()

        container.run_gate("origin/develop", tmp_path, docker, root)

        args = docker.run_args()
        user = args[args.index("--user") + 1]
        assert user.split(":")[0] != "0"


class TestRunGate:
    def test_a_passing_gate_returns_the_tail_of_its_output(self, root: Path, tmp_path: Path) -> None:
        output = "\n".join(f"line {n}" for n in range(40))

        passed, tail = container.run_gate("origin/develop", tmp_path, FakeDocker(gate=completed(output)), root)

        assert passed and tail.splitlines() == [f"line {n}" for n in range(25, 40)]

    def test_a_failing_gate_is_red(self, root: Path, tmp_path: Path) -> None:
        gate = completed("FAIL: ruff", returncode=1)

        passed, tail = container.run_gate("origin/develop", tmp_path, FakeDocker(gate=gate), root)

        assert not passed and tail == "FAIL: ruff"

    def test_a_gate_that_outlives_its_timeout_is_red_and_its_container_is_killed_by_name(
        self, root: Path, tmp_path: Path
    ) -> None:
        docker = FakeDocker()
        docker.timeout_on_run = True

        result = container.run_gate("origin/develop", tmp_path, docker, root)

        run_args = docker.run_args()
        name = run_args[run_args.index("--name") + 1]
        assert result == (False, "The gate timed out.")
        assert docker.calls[-1][0] == ["docker", "kill", name]

    def test_a_failed_kill_does_not_hide_the_timeout(self, root: Path, tmp_path: Path) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            if args[1] == "run":
                raise subprocess.TimeoutExpired("docker", timeout)
            if args[1] == "kill":
                raise OSError("daemon gone")
            return completed()

        assert container.run_gate("origin/develop", tmp_path, runner, root) == (False, "The gate timed out.")

    def test_each_run_gets_its_own_container_name(self, root: Path, tmp_path: Path) -> None:
        first, second = FakeDocker(), FakeDocker()

        container.run_gate("origin/develop", tmp_path, first, root)
        container.run_gate("origin/develop", tmp_path, second, root)

        names = [d.run_args()[d.run_args().index("--name") + 1] for d in (first, second)]
        assert names[0] != names[1] and all(n.startswith("forge-gate-") for n in names)


@dataclass(frozen=True)
class AgentTask:
    prompt: str
    cwd: Path
    files: tuple[Path, ...]


TOKEN = "test-token-value-for-redaction"
ENVIRON = {container.CLAUDE_AUTH_VARIABLE: TOKEN}


def agent_result(text: str = "done", is_error: bool = False) -> subprocess.CompletedProcess[str]:
    payload = {"is_error": is_error, "result": text, "num_turns": 3, "duration_ms": 10, "permission_denials": []}
    return completed(json.dumps(payload), returncode=1 if is_error else 0)


@pytest.fixture
def task(tmp_path: Path) -> AgentTask:
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    questions, summary = exchange / "questions.md", exchange / "summary.md"
    prompt = f"Work in the repo. Write questions to {questions} and a summary to {summary}."
    return AgentTask(prompt, tmp_path / "clone", (questions, summary))


class TestAgentImage:
    def test_it_builds_the_agent_stage_of_the_same_dockerfile_in_one_build(self, root: Path) -> None:
        docker = FakeDocker(image_present=False)

        tag = container.ensure_agent_image(root, docker)

        assert tag == container.agent_image_tag(root) and tag.startswith("trading-agent:")
        assert docker.verbs() == ["image", "build"]
        build = docker.calls[1][0]
        assert build[build.index("--target") + 1] == "agent"
        assert f"CLAUDE_CODE_VERSION={container.CLAUDE_CODE_VERSION}" in build
        assert set(docker.built_files) == {"Dockerfile", "requirements-base.txt", "requirements-dev.txt"}

    def test_the_gate_stage_is_built_with_no_build_arguments(self, root: Path) -> None:
        docker = FakeDocker(image_present=False)

        container.ensure_image(root, docker)

        build = docker.calls[1][0]
        assert build[build.index("--target") + 1] == "gate" and "--build-arg" not in build

    def test_existing_images_are_reused(self, root: Path) -> None:
        docker = FakeDocker(image_present=True)

        container.ensure_agent_image(root, docker)

        assert docker.verbs() == ["image"]

    def test_the_tag_changes_with_the_agent_dockerfile_the_gate_requirements_and_the_pinned_version(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = container.agent_image_tag(root)
        (root / "docker" / "Dockerfile").write_text("FROM python:3.14-slim AS gate\nRUN true\n", encoding="utf-8")
        second = container.agent_image_tag(root)
        (root / "requirements-base.txt").write_text("numpy==2\n", encoding="utf-8")
        third = container.agent_image_tag(root)
        monkeypatch.setattr(container, "CLAUDE_CODE_VERSION", "9.9.9")
        fourth = container.agent_image_tag(root)

        assert len({first, second, third, fourth}) == 4

    def test_the_pinned_version_is_the_one_the_workflow_installs(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "pr-readiness.yml").read_text(encoding="utf-8")

        match = WORKFLOW_PINNED_VERSION.search(workflow)

        assert match and match.group(1) == container.CLAUDE_CODE_VERSION


class TestAgentCommand:
    def _args(self, root: Path, task: AgentTask, **kwargs: object) -> list[str]:
        docker = FakeDocker(gate=agent_result())
        container.run_agent(task, runner=docker, root=root, environ=ENVIRON, **kwargs)  # type: ignore[arg-type]
        return docker.run_args()

    def test_the_network_is_open_but_the_isolation_flags_are_the_gates(self, root: Path, task: AgentTask) -> None:
        args = self._args(root, task)
        joined = " ".join(args)

        assert "--network" not in args
        for flag in ("--read-only", "--cap-drop ALL", "--security-opt no-new-privileges", "--rm", "--init", "-i"):
            assert flag in joined
        assert f"--memory {container.MEMORY}" in joined and f"--pids-limit {container.PIDS_LIMIT}" in joined
        assert not any(arg in ("--privileged", "--env-file", "--pid", "--volume", "-v") for arg in args)

    def test_only_the_clone_and_the_exchange_directory_are_mounted(self, root: Path, task: AgentTask) -> None:
        args = self._args(root, task)

        mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
        assert mounts == [
            f"type=bind,source={task.cwd},target=/work",
            f"type=bind,source={task.files[0].parent},target=/exchange",
        ]

    def test_the_token_is_passed_by_name_and_its_value_is_on_no_command_line(
        self, root: Path, task: AgentTask
    ) -> None:
        args = self._args(root, task)

        assert "CLAUDE_CODE_OAUTH_TOKEN" in args and not any(TOKEN in arg for arg in args)
        names = {args[i + 1].split("=", 1)[0] for i, arg in enumerate(args) if arg == "--env"}
        assert names == {
            "PATH",
            "VIRTUAL_ENV",
            "PYTHONPATH",
            "LANG",
            "HOME",
            "PYTHONDONTWRITEBYTECODE",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_TERMINAL_PROMPT",
            "GIT_ALLOW_PROTOCOL",
            "CLAUDE_CODE_OAUTH_TOKEN",
        }

    def test_git_reads_no_configuration_but_trusting_the_mount_and_may_only_use_files(
        self, root: Path, task: AgentTask
    ) -> None:
        args = self._args(root, task)

        assert "GIT_CONFIG_GLOBAL=/dev/null" in args and "GIT_CONFIG_NOSYSTEM=1" in args
        assert "GIT_CONFIG_KEY_0=safe.directory" in args and "GIT_CONFIG_VALUE_0=/work" in args
        assert "GIT_ALLOW_PROTOCOL=file" in args

    def test_the_owners_name_and_email_become_the_commit_author(self, root: Path, task: AgentTask) -> None:
        args = self._args(root, task, identity=("Ada", "ada@example.test"))

        assert {"GIT_AUTHOR_NAME=Ada", "GIT_COMMITTER_EMAIL=ada@example.test"} <= set(args)

    def test_claude_gets_the_same_tool_lists_as_on_the_host_and_the_model(self, root: Path, task: AgentTask) -> None:
        from scripts.forge import tools

        args = self._args(root, task, model="sonnet")

        assert args[args.index("--allowedTools") + 1] == tools.ALLOWED_TOOLS
        assert args[args.index("--disallowedTools") + 1] == tools.DENIED_TOOLS
        assert args[args.index("--model") + 1] == "sonnet"
        assert args[args.index("-p") - 1].startswith("trading-agent:")

    def test_anything_outside_the_allow_list_is_denied_not_prompted_for(self, root: Path, task: AgentTask) -> None:
        args = self._args(root, task)

        assert args[args.index("--permission-mode") + 1] == "dontAsk"
        assert args[args.index("--permission-prompts") + 1] == "none"
        assert "bypassPermissions" not in args and "--dangerously-skip-permissions" not in args

    def test_mcp_servers_from_the_repository_are_never_used(self, root: Path, task: AgentTask) -> None:
        assert "--strict-mcp-config" in self._args(root, task) and "--mcp-config" not in self._args(root, task)

    def test_no_model_flag_without_a_model(self, root: Path, task: AgentTask) -> None:
        assert "--model" not in self._args(root, task)


class TestDaemonAndPreflight:
    @pytest.mark.parametrize(
        "stderr",
        [
            "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine",
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
            "error during connect: Get http://x: dial tcp",
            "Is the docker daemon running?",
        ],
    )
    def test_a_daemon_that_is_not_running_is_named_not_mistaken_for_a_missing_image(
        self, root: Path, stderr: str
    ) -> None:
        calls: list[str] = []

        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(args[1])
            return completed(returncode=1, stderr=stderr)

        with pytest.raises(ForgeError, match="daemon is not running.*--no-container"):
            container.ensure_image(root, runner)

        assert calls == ["image"]

    def test_the_agent_image_check_also_names_a_daemon_that_is_not_running(self, root: Path) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            return completed(returncode=1, stderr="error during connect: dial tcp")

        with pytest.raises(ForgeError, match="daemon is not running"):
            container.ensure_agent_image(root, runner)

    def test_an_inspect_failure_that_is_not_the_daemon_still_goes_on_to_build(self, root: Path) -> None:
        calls: list[str] = []

        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(args[1])
            if args[1] == "image":
                return completed(returncode=1, stderr="Error response from daemon: No such image: trading-gate:x")
            return completed()

        container.ensure_image(root, runner)

        assert calls == ["image", "build"]

    def test_the_gate_preflight_checks_only_the_gate_image(self, root: Path) -> None:
        docker = FakeDocker(image_present=True)

        container.preflight(root, gate=True, agent=False, runner=docker, environ={})

        assert docker.verbs() == ["image"]

    def test_the_agent_preflight_checks_both_images_and_the_token(self, root: Path) -> None:
        docker = FakeDocker(image_present=True)

        container.preflight(root, gate=True, agent=True, runner=docker, environ=ENVIRON)

        assert docker.verbs() == ["image", "image"]

    def test_the_agent_preflight_stops_on_a_missing_token_before_touching_docker(self, root: Path) -> None:
        docker = FakeDocker()

        with pytest.raises(ForgeError, match="setup-token"):
            container.preflight(root, gate=True, agent=True, runner=docker, environ={})

        assert docker.calls == []

    def test_a_missing_image_is_built_by_the_preflight_so_the_run_does_not_pay_for_it(self, root: Path) -> None:
        docker = FakeDocker(image_present=False)

        container.preflight(root, gate=True, agent=False, runner=docker, environ={})

        assert docker.verbs() == ["image", "build"]


class TestUserAndStop:
    def test_the_container_user_is_a_fixed_non_root_id_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(container.sys, "platform", "win32")

        assert container._user() == f"{container.NON_ROOT_UID}:{container.NON_ROOT_UID}"

    def test_the_container_user_is_the_owners_id_on_posix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(container.sys, "platform", "linux")
        monkeypatch.setattr(container.os, "getuid", lambda: 1234, raising=False)
        monkeypatch.setattr(container.os, "getgid", lambda: 5678, raising=False)

        assert container._user() == "1234:5678"

    def test_a_kill_that_fails_says_which_container_may_still_be_running(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            return completed(returncode=1, stderr="daemon unresponsive")

        container._kill_container(runner, "forge-agent-abc")

        err = capsys.readouterr().err
        assert "forge-agent-abc" in err and "docker rm -f forge-agent-abc" in err

    def test_a_kill_that_cannot_reach_docker_says_the_same(self, capsys: pytest.CaptureFixture[str]) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            raise OSError("pipe closed")

        container._kill_container(runner, "forge-gate-xyz")

        assert "docker rm -f forge-gate-xyz" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "stderr",
        ["Error response from daemon: No such container: forge-agent-abc", "Error: container is not running"],
    )
    def test_a_container_that_is_already_gone_is_not_reported_as_still_running(
        self, stderr: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            return completed(returncode=1, stderr=stderr)

        container._kill_container(runner, "forge-agent-abc")

        assert capsys.readouterr().err == ""

    def test_a_kill_that_works_says_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        container._kill_container(FakeDocker(), "forge-agent-abc")

        assert capsys.readouterr().err == ""


class TestMountPaths:
    def test_a_clone_path_with_a_comma_is_refused_before_anything_runs(self, root: Path, tmp_path: Path) -> None:
        docker = FakeDocker()

        with pytest.raises(ForgeError, match="comma"):
            container.run_gate("origin/develop", tmp_path / "a,readonly=false", docker, root)

        assert "run" not in docker.verbs()

    def test_an_exchange_path_with_a_comma_is_refused_for_the_agent(self, root: Path, task: AgentTask) -> None:
        bad = AgentTask(task.prompt, task.cwd, (task.files[0].parent / "x,y" / "q.md",))
        docker = FakeDocker(gate=agent_result())

        with pytest.raises(ForgeError, match="comma"):
            container.run_agent(bad, runner=docker, root=root, environ=ENVIRON)

        assert "run" not in docker.verbs()


class TestRunAgent:
    def test_the_prompt_goes_in_on_stdin_with_host_paths_rewritten_to_the_exchange_mount(
        self, root: Path, task: AgentTask
    ) -> None:
        docker = FakeDocker(gate=agent_result())

        container.run_agent(task, runner=docker, root=root, environ=ENVIRON)

        sent = next(text for text in docker.inputs if text)
        assert "/exchange/questions.md" in sent and "/exchange/summary.md" in sent
        assert str(task.files[0]) not in sent and str(task.files[0].parent) not in sent

    def test_without_a_token_it_stops_before_touching_docker(self, root: Path, task: AgentTask) -> None:
        docker = FakeDocker()

        with pytest.raises(ForgeError, match="setup-token"):
            container.run_agent(task, runner=docker, root=root, environ={})

        assert docker.calls == []

    def test_files_in_different_directories_cannot_be_mounted(
        self, root: Path, task: AgentTask, tmp_path: Path
    ) -> None:
        split = AgentTask(task.prompt, task.cwd, (task.files[0], tmp_path / "elsewhere" / "summary.md"))

        with pytest.raises(ForgeError, match="one directory"):
            container.run_agent(split, runner=FakeDocker(), root=root, environ=ENVIRON)

    def test_a_session_that_outlives_its_timeout_is_stopped_by_name(self, root: Path, task: AgentTask) -> None:
        docker = FakeDocker()
        docker.timeout_on_run = True

        with pytest.raises(ForgeError, match="timed out"):
            container.run_agent(task, runner=docker, root=root, environ=ENVIRON)

        run_args = docker.run_args()
        name = run_args[run_args.index("--name") + 1]
        assert docker.calls[-1][0] == ["docker", "kill", name] and name.startswith("forge-agent-")

    def test_an_agent_error_is_a_forge_error_with_the_agents_text(self, root: Path, task: AgentTask) -> None:
        docker = FakeDocker(gate=agent_result("Not logged in", is_error=True))

        with pytest.raises(ForgeError, match="Not logged in"):
            container.run_agent(task, runner=docker, root=root, environ=ENVIRON)

    def test_a_successful_session_prints_the_one_line_summary(
        self, root: Path, task: AgentTask, capsys: pytest.CaptureFixture[str]
    ) -> None:
        container.run_agent(task, runner=FakeDocker(gate=agent_result()), root=root, environ=ENVIRON)

        assert "Agent: 3 turns" in capsys.readouterr().err

    def test_the_token_is_redacted_from_anything_the_agent_echoes(self, root: Path, task: AgentTask) -> None:
        docker = FakeDocker(gate=agent_result(f"my token is {TOKEN}", is_error=True))

        with pytest.raises(ForgeError) as raised:
            container.run_agent(task, runner=docker, root=root, environ=ENVIRON)

        assert TOKEN not in str(raised.value) and "<token>" in str(raised.value)

    def test_a_missing_docker_client_says_so(self, root: Path, task: AgentTask) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            if args[1] == "run":
                raise FileNotFoundError("docker")
            return completed()

        with pytest.raises(ForgeError, match="Docker could not be started.*run without --agent-container"):
            container.run_agent(task, runner=runner, root=root, environ=ENVIRON)


class TestRepositoryFiles:
    def test_the_real_dockerfile_and_requirements_produce_a_tag(self) -> None:
        assert container.image_tag(REPO_ROOT).startswith("trading-gate:")

    def test_the_real_dockerfile_installs_the_requirements_it_is_given_and_does_not_run_as_root(self) -> None:
        text = (REPO_ROOT / container.DOCKERFILE).read_text(encoding="utf-8")

        assert "requirements-dev.txt" in text and "USER gate" in text and "safe.directory /work" in text

    def test_the_real_dockerfile_has_exactly_the_stages_the_runner_builds(self) -> None:
        text = (REPO_ROOT / container.DOCKERFILE).read_text(encoding="utf-8")
        stages = DOCKERFILE_STAGE.findall(text)

        assert stages == ["gate", "node", "agent"]
        assert text.count("ENTRYPOINT") == 1 and text.index("ENTRYPOINT") > text.index("FROM gate AS agent")


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is not installed")
class TestWithDocker:
    """Run against the real daemon; skipped when Docker is absent or not running."""

    @pytest.fixture(scope="class")
    def image(self) -> str:
        if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
            pytest.skip("The Docker daemon is not running")
        return container.ensure_image(REPO_ROOT)

    def _run(self, image: str, clone: Path, *command: str) -> subprocess.CompletedProcess[str]:
        args = container.gate_command(image, f"forge-gate-test-{uuid.uuid4().hex[:8]}", clone, "unused")
        head = args[: args.index(image) + 1]
        return subprocess.run(["docker", *head, *command], capture_output=True, text=True, check=False, timeout=120)

    def test_the_network_is_unreachable(self, image: str, tmp_path: Path) -> None:
        probe = "import socket; socket.create_connection(('1.1.1.1', 53), 3)"

        result = self._run(image, tmp_path, "python", "-c", probe)

        assert result.returncode != 0

    def test_a_file_outside_the_mount_and_the_host_environment_are_invisible(
        self, image: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "secret.txt").write_text("planted", encoding="utf-8")
        clone = tmp_path / "clone"
        clone.mkdir()
        monkeypatch.setenv("FORGE_PLANTED_SECRET", "hunter2")
        script = (
            "import os, pathlib; "
            "print(sorted(k for k in os.environ if 'SECRET' in k)); "
            "print(any(os.path.exists(p) for p in (r'%s', '/secret.txt', '/host')))" % (tmp_path / "secret.txt")
        )

        result = self._run(image, clone, "python", "-c", script)

        assert result.returncode == 0
        assert result.stdout.split("\n")[0] == "[]" and "False" in result.stdout and "planted" not in result.stdout

    def test_the_root_filesystem_is_read_only_but_the_clone_and_tmp_are_writable(
        self, image: str, tmp_path: Path
    ) -> None:
        clone = tmp_path / "clone"
        clone.mkdir()
        script = (
            "import pathlib\n"
            "pathlib.Path('/work/ok.txt').write_text('x'); pathlib.Path('/tmp/ok.txt').write_text('x')\n"
            "try:\n    pathlib.Path('/usr/ro.txt').write_text('x')\nexcept OSError:\n    print('read-only')\n"
        )

        result = self._run(image, clone, "python", "-c", script)

        assert "read-only" in result.stdout and (clone / "ok.txt").exists()

    def test_a_timeout_kills_the_container(self, image: str, tmp_path: Path) -> None:
        def runner(args: list[str], timeout: float, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
            if args[1] == "run":
                args = [*args[: args.index(image) + 1], "sleep", "300"]
                timeout = 3
            return container.docker_runner(args, timeout)

        result = container.run_gate("unused", tmp_path, runner)

        names = subprocess.run(
            ["docker", "ps", "--filter", "name=forge-gate-", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        assert result == (False, "The gate timed out.") and names == []


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is not installed")
class TestAgentWithDocker:
    """Run against the real daemon; the first run builds the agent image and needs the network once."""

    @pytest.fixture(scope="class")
    def image(self) -> str:
        if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
            pytest.skip("The Docker daemon is not running")
        return container.ensure_agent_image(REPO_ROOT)

    def _run(
        self, image: str, clone: Path, *command: str, entrypoint: str | None = None
    ) -> "subprocess.CompletedProcess[str]":
        name = f"forge-agent-test-{uuid.uuid4().hex[:8]}"
        args = ["docker", "run", "--network", "none", *container._isolation(name, clone)]
        args += ["--entrypoint", entrypoint] if entrypoint else []
        return subprocess.run([*args, image, *command], capture_output=True, text=True, check=False, timeout=300)

    def test_the_entrypoint_makes_a_venv_in_the_clone_and_starts_the_pinned_claude(
        self, image: str, tmp_path: Path
    ) -> None:
        result = self._run(image, tmp_path, "--version")

        assert result.returncode == 0 and container.CLAUDE_CODE_VERSION in result.stdout
        assert (tmp_path / ".venv" / "pyvenv.cfg").is_file()

    def test_the_venv_the_entrypoint_made_sees_the_installed_requirements(self, image: str, tmp_path: Path) -> None:
        assert self._run(image, tmp_path, "--version").returncode == 0

        result = self._run(image, tmp_path, "-c", ".venv/bin/python -c 'import pytest, mypy'", entrypoint="sh")

        assert result.returncode == 0, result.stderr

    def test_the_pinned_cli_lists_every_flag_the_agent_command_passes(self, image: str, tmp_path: Path) -> None:
        command = container.agent_command(image, "forge-agent-flags", tmp_path, tmp_path, None, "sonnet")
        flags = [arg for arg in command[command.index(image) + 1 :] if arg.startswith("--")]
        help_text = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "claude", image, "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        ).stdout

        assert flags and [flag for flag in flags if flag not in help_text] == []
        assert container.PERMISSION_MODE in help_text and f'"{container.PERMISSION_PROMPTS}"' in help_text

    def test_the_host_can_delete_a_clone_the_container_made_a_venv_in(self, image: str, tmp_path: Path) -> None:
        clone = tmp_path / "clone"
        clone.mkdir()
        (clone / "tracked.txt").write_text("x", encoding="utf-8")
        assert self._run(image, clone, "--version").returncode == 0

        shutil.rmtree(clone)

        assert not clone.exists()
