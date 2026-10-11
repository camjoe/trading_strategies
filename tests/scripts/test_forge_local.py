import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.forge import local
from scripts.forge.base import ForgeError
from scripts.forge.fix_loop import RoundTask

TASK = RoundTask(7, "origin/develop", "prompt", Path("old.md"), Path("new.md"), Path("."))


def completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["claude"], returncode, stdout, stderr)


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local, "get_repo_root", lambda: Path("."))


class TestRunClaudeAgent:
    def test_a_successful_round_prints_a_one_line_summary(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = {"is_error": False, "num_turns": 16, "duration_ms": 60689, "permission_denials": [{}, {}]}
        monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(json.dumps(result)))

        local.run_claude_agent(TASK)

        err = capsys.readouterr().err
        assert "16 turns" in err
        assert "2 permission denials" in err

    def test_the_agents_own_error_text_is_the_failure_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = {"is_error": True, "result": "Not logged in · Please run /login"}
        monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(json.dumps(result), returncode=1))

        with pytest.raises(ForgeError, match="Not logged in"):
            local.run_claude_agent(TASK)

    def test_unparseable_output_falls_back_to_stderr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed("not json", 1, "boom"))

        with pytest.raises(ForgeError, match="boom"):
            local.run_claude_agent(TASK)

    def test_a_missing_claude_cli_is_a_forge_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def missing(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError

        monkeypatch.setattr(local.subprocess, "run", missing)

        with pytest.raises(ForgeError, match="not installed"):
            local.run_claude_agent(TASK)

    def test_a_timeout_is_a_forge_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def slow(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("claude", 1)

        monkeypatch.setattr(local.subprocess, "run", slow)

        with pytest.raises(ForgeError, match="timed out"):
            local.run_claude_agent(TASK)

    def test_the_agent_may_run_the_repo_test_runner_and_may_not_push(self) -> None:
        assert "Bash(.venv/Scripts/pytest.exe:*)" in local._ALLOWED_TOOLS
        assert "Bash(git push:*)" in local._DENIED_TOOLS


class TestEmailNotifier:
    def test_says_so_when_no_smtp_settings_are_set(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("HOST", "FROM", "TO"):
            monkeypatch.delenv(f"TRADING_RUNTIME_ALERT_SMTP_{name}", raising=False)

        local.email_notifier("subject", "message", {"outcome": "ready"})

        assert "SMTP settings are not set" in capsys.readouterr().err

    def test_sends_through_the_runtime_notifier_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent: list[dict[str, object]] = []
        monkeypatch.setattr(local, "resolve_email_config_from_env", lambda: object())
        monkeypatch.setattr(local, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)

        local.email_notifier("subject", "message", {"outcome": "ready"})

        assert sent[0]["status"] == "ok" and sent[0]["event"] == "pr-readiness-loop"

    def test_a_failed_send_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(local, "resolve_email_config_from_env", lambda: object())
        monkeypatch.setattr(local, "notify_runtime_event", lambda **kwargs: False)

        local.email_notifier("subject", "message", {"outcome": "stopped"})

        assert "delivery failed" in capsys.readouterr().err


class TestModelOption:
    def _command_for(self, monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> list[str]:
        seen: list[list[str]] = []

        def run(command: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            return completed(json.dumps({"is_error": False}))

        monkeypatch.setattr(local.subprocess, "run", run)
        local.run_claude_agent(TASK, **kwargs)  # type: ignore[arg-type]
        return next(command for command in seen if command[0] == "claude")

    def test_the_model_is_passed_to_claude(self, monkeypatch: pytest.MonkeyPatch) -> None:
        command = self._command_for(monkeypatch, model="sonnet")

        assert command[command.index("--model") + 1] == "sonnet"

    def test_without_a_model_claude_uses_its_own_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert "--model" not in self._command_for(monkeypatch)


def test_the_fix_loop_command_defaults_to_sonnet() -> None:
    from scripts.forge.cli import build_parser

    assert build_parser().parse_args(["fix-loop", "--pr", "1"]).model == "sonnet"
    assert build_parser().parse_args(["fix-loop", "--pr", "1", "--model", "opus"]).model == "opus"


def test_each_denied_command_is_listed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    denial = {"tool_name": "Bash", "tool_input": {"command": "cp a b"}}
    result = {"is_error": False, "num_turns": 1, "duration_ms": 1, "permission_denials": [denial]}
    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(json.dumps(result)))

    local.run_claude_agent(TASK)

    assert "denied: cp a b" in capsys.readouterr().err


class TestToolLimits:
    def test_python_is_allowed_only_for_the_checks_and_the_test_runner(self) -> None:
        allowed = local._ALLOWED_TOOLS.split(",")

        assert "Bash(python:*)" not in allowed and "Bash(.venv/Scripts/python.exe:*)" not in allowed
        assert "Bash(.venv/Scripts/python.exe -m scripts.run_checks:*)" in allowed
        assert "Bash(python -m pytest:*)" in allowed

    def test_the_agent_cannot_write_into_git_or_reach_the_remote(self) -> None:
        denied = local._DENIED_TOOLS.split(",")

        for item in ("Edit(.git/**)", "Write(.git/**)", "Bash(gh:*)", "Bash(git push:*)", "Bash(git config:*)"):
            assert item in denied

    def test_nothing_is_both_allowed_and_denied(self) -> None:
        assert not set(local._ALLOWED_TOOLS.split(",")) & set(local._DENIED_TOOLS.split(","))


class TestAgentEnvironment:
    def _env(self, tmp_path: Path, identity: tuple[str, str] | None = ("Dev", "dev@example.test")) -> dict[str, str]:
        base = {
            "PATH": "/bin",
            "GH_TOKEN": "x",
            "GITHUB_TOKEN": "x",
            "AWS_SECRET_ACCESS_KEY": "x",
            "SOME_API_KEY": "x",
            "TRADING_RUNTIME_ALERT_SMTP_PASSWORD": "x",
            "SSH_AUTH_SOCK": "/tmp/agent",
            "CLAUDE_CODE_OAUTH_TOKEN": "keep",
            "ANTHROPIC_API_KEY": "keep",
        }
        return local.agent_environment(base, tmp_path, identity)

    def test_secret_looking_variables_are_removed_but_the_claude_ones_stay(self, tmp_path: Path) -> None:
        env = self._env(tmp_path)

        for name in ("GH_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SOME_API_KEY", "SSH_AUTH_SOCK"):
            assert name not in env
        assert "TRADING_RUNTIME_ALERT_SMTP_PASSWORD" not in env
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "keep" and env["ANTHROPIC_API_KEY"] == "keep"
        assert env["PATH"] == "/bin"

    def test_git_gets_an_empty_configuration_and_may_only_use_local_files(self, tmp_path: Path) -> None:
        env = self._env(tmp_path)

        assert Path(env["GIT_CONFIG_GLOBAL"]).read_text(encoding="utf-8") == ""
        assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_ALLOW_PROTOCOL"] == "file"
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_gh_reads_an_empty_configuration_directory(self, tmp_path: Path) -> None:
        config = Path(self._env(tmp_path)["GH_CONFIG_DIR"])

        assert config.is_dir() and list(config.iterdir()) == []

    def test_commits_still_carry_the_owners_identity(self, tmp_path: Path) -> None:
        env = self._env(tmp_path)

        assert env["GIT_AUTHOR_NAME"] == env["GIT_COMMITTER_NAME"] == "Dev"
        assert env["GIT_AUTHOR_EMAIL"] == env["GIT_COMMITTER_EMAIL"] == "dev@example.test"

    def test_without_an_identity_none_is_invented(self, tmp_path: Path) -> None:
        assert "GIT_AUTHOR_NAME" not in self._env(tmp_path, identity=None)

    def test_a_real_git_push_from_the_scrubbed_environment_cannot_reach_a_remote(self, tmp_path: Path) -> None:
        import subprocess as sp

        repo = tmp_path / "repo"
        repo.mkdir()
        sp.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        sp.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"],
            cwd=repo,
            check=True,
        )
        sp.run(["git", "remote", "add", "origin", "https://github.com/example/none.git"], cwd=repo, check=True)
        scratch = tmp_path / "scratch"
        scratch.mkdir()

        pushed = sp.run(
            ["git", "push", "origin", "HEAD:refs/heads/x"],
            cwd=repo,
            env=local.agent_environment(os.environ, scratch),
            capture_output=True,
            text=True,
        )

        assert pushed.returncode != 0 and "not allowed" in pushed.stderr


class TestLocalGitHelpers:
    def test_exists_on_reports_whether_a_path_is_in_the_tree_at_a_ref(self, tmp_path: Path) -> None:
        import subprocess as sp

        sp.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
        sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        sp.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
        (tmp_path / "plan").mkdir()
        (tmp_path / "plan" / "x.md").write_text("x", encoding="utf-8")
        sp.run(["git", "add", "."], cwd=tmp_path, check=True)
        sp.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
        git = local.LocalGit(tmp_path)

        assert git.exists_on("HEAD", "plan/x.md") and not git.exists_on("HEAD", "plan/missing.md")

    def test_a_failing_git_command_becomes_a_forge_error(self, tmp_path: Path) -> None:
        with pytest.raises(local.ForgeError, match="git"):
            local.LocalGit(tmp_path).head()


class TestAgentRunsInTheSandbox:
    def test_the_session_starts_in_the_tasks_directory_with_its_virtual_environment_active(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: dict[str, object] = {}

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.update(kwargs)
            return completed(json.dumps({"is_error": False}))

        monkeypatch.setattr(local.subprocess, "run", run)
        task = RoundTask(7, "origin/develop", "prompt", Path("old.md"), Path("new.md"), tmp_path)

        local.run_claude_agent(task)

        env = seen["env"]
        assert seen["cwd"] == tmp_path and isinstance(env, dict)
        assert env["VIRTUAL_ENV"] == str(tmp_path / ".venv")
        assert env["PATH"].startswith(str(local.venv_python(tmp_path / ".venv").parent))

    def test_the_owners_virtual_environment_and_python_home_are_replaced(self, tmp_path: Path) -> None:
        base = {"PATH": "/bin", "VIRTUAL_ENV": "/owner/.venv", "PYTHONHOME": "/owner/py"}

        env = local.agent_environment(base, tmp_path, workdir=tmp_path / "box")

        assert env["VIRTUAL_ENV"] == str(tmp_path / "box" / ".venv") and "PYTHONHOME" not in env
        assert env["PATH"].endswith(os.pathsep + "/bin")

    def test_without_a_workdir_the_path_is_left_alone(self, tmp_path: Path) -> None:
        env = local.agent_environment({"PATH": "/bin", "VIRTUAL_ENV": "/owner/.venv"}, tmp_path)

        assert env["PATH"] == "/bin" and env["VIRTUAL_ENV"] == "/owner/.venv"


class TestRunGate:
    def test_it_runs_the_checks_with_this_interpreter_in_the_clone_and_puts_the_clones_source_first(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: dict[str, object] = {}

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen["command"] = command
            seen.update(kwargs)
            return completed("all good")

        monkeypatch.setattr(local.subprocess, "run", run)

        passed, tail = local.run_gate("origin/develop", tmp_path)

        assert passed and tail == "all good"
        assert seen["command"] == [local.sys.executable, "-m", "scripts.run_checks", "pr", "--base", "origin/develop"]
        assert seen["cwd"] == tmp_path
        assert str(seen["env"]["PYTHONPATH"]).startswith(str(tmp_path / "src"))  # type: ignore[index]

    def test_a_failing_gate_reports_the_tail_of_its_output(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        output = "\n".join(f"line {number}" for number in range(40))
        monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(output, returncode=1))

        passed, tail = local.run_gate("origin/develop", tmp_path)

        assert not passed and tail.splitlines() == [f"line {number}" for number in range(25, 40)]

    def test_a_gate_that_never_finishes_is_red(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        def slow(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("gate", 1)

        monkeypatch.setattr(local.subprocess, "run", slow)

        assert local.run_gate("origin/develop", tmp_path) == (False, "The gate timed out.")
