import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from scripts.forge import container
from scripts.forge.base import ForgeError

REPO_ROOT = Path(__file__).resolve().parents[2]


def completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["docker"], returncode, stdout, stderr)


class FakeDocker:
    """Records each Docker client call; ``image_present`` answers ``image inspect``."""

    def __init__(self, image_present: bool = True, gate: subprocess.CompletedProcess[str] | None = None) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self.image_present = image_present
        self.gate = gate or completed("ok")
        self.timeout_on_run = False
        self.built_files: dict[str, str] = {}

    def __call__(self, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, timeout))
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
    (repo / "docker" / "gate").mkdir(parents=True)
    (repo / "docker" / "gate" / "Dockerfile").write_text("FROM python:3.14-slim\n", encoding="utf-8")
    (repo / "requirements-base.txt").write_text("numpy==1\n", encoding="utf-8")
    (repo / "requirements-dev.txt").write_text("-r requirements-base.txt\npytest==9\n-e .\n", encoding="utf-8")
    return repo


class TestImageTag:
    def test_it_changes_with_the_requirements_and_the_dockerfile_and_not_otherwise(self, root: Path) -> None:
        first = container.image_tag(root)

        assert container.image_tag(root) == first
        (root / "requirements-base.txt").write_text("numpy==2\n", encoding="utf-8")
        second = container.image_tag(root)
        (root / "docker" / "gate" / "Dockerfile").write_text("FROM python:3.15-slim\n", encoding="utf-8")
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
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            return completed(returncode=1 if args[1] == "image" else 1, stderr="step 1\nno space left")

        with pytest.raises(ForgeError, match="could not be built: no space left"):
            container.ensure_image(root, runner)

    def test_a_missing_docker_client_says_so(self, root: Path) -> None:
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("docker")

        with pytest.raises(ForgeError, match="needs Docker"):
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

    def test_the_container_does_not_run_as_root(self, root: Path, tmp_path: Path) -> None:
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
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
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


class TestRepositoryFiles:
    def test_the_real_dockerfile_and_requirements_produce_a_tag(self) -> None:
        assert container.image_tag(REPO_ROOT).startswith("trading-gate:")

    def test_the_real_dockerfile_installs_the_requirements_it_is_given_and_does_not_run_as_root(self) -> None:
        text = (REPO_ROOT / container.DOCKERFILE).read_text(encoding="utf-8")

        assert "requirements-dev.txt" in text and "USER gate" in text and "safe.directory /work" in text


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
        def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
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
