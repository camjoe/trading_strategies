import json
import os
import smtplib
import subprocess
from pathlib import Path

import pytest

from scripts.forge import local, tools
from scripts.forge.base import ForgeError
from scripts.forge.fix_loop import RoundTask
from trading.interfaces.runtime import notifications
from trading.interfaces.runtime.jobs import job_helpers

TASK = RoundTask("prompt", Path("old.md"), Path("new.md"), Path("."))


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
        assert "Bash(.venv/Scripts/pytest.exe:*)" in tools.ALLOWED_TOOLS
        assert "Bash(git push:*)" in tools.DENIED_TOOLS


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
        monkeypatch.setattr(job_helpers, "resolve_email_config_from_env", lambda: object())
        monkeypatch.setattr(notifications, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)

        local.email_notifier("subject", "message", {"outcome": "ready"})

        assert sent[0]["status"] == "ok" and sent[0]["event"] == "pr-readiness-loop"

    def test_a_failed_send_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(job_helpers, "resolve_email_config_from_env", lambda: object())
        monkeypatch.setattr(notifications, "notify_runtime_event", lambda **kwargs: False)

        local.email_notifier("subject", "message", {"outcome": "stopped"})

        assert "delivery failed" in capsys.readouterr().err


class TestHostAgentCommand:
    def _command_for(self, monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> list[str]:
        seen: list[list[str]] = []

        def run(command: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            return completed(json.dumps({"is_error": False}))

        monkeypatch.setattr(local.subprocess, "run", run)
        local.run_claude_agent(TASK, **kwargs)  # type: ignore[arg-type]
        return next(command for command in seen if command[0] == "claude")

    def test_it_denies_what_the_allow_list_leaves_out_instead_of_prompting_and_ignores_repository_mcp_servers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        command = self._command_for(monkeypatch)
        options = list(tools.DENY_BY_DEFAULT_OPTIONS)
        start = command.index(options[0])

        assert command[start : start + len(options)] == options
        assert "--mcp-config" not in command
        assert "bypassPermissions" not in command and "--dangerously-skip-permissions" not in command

    def test_the_model_is_passed_to_claude(self, monkeypatch: pytest.MonkeyPatch) -> None:
        command = self._command_for(monkeypatch, model="sonnet")

        assert command[command.index("--model") + 1] == "sonnet"

    def test_without_a_model_claude_uses_its_own_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert "--model" not in self._command_for(monkeypatch)


def test_the_agent_container_flag_chooses_the_container_runner_and_keeps_the_model_and_identity() -> None:
    from scripts.forge import cli, container
    from scripts.forge.cli import build_parser

    class FakeGit:
        def identity(self) -> tuple[str, str]:
            return ("Ada", "ada@example.test")

    contained = cli._agent(build_parser().parse_args(["fix-loop", "--pr", "1", "--agent-container"]), FakeGit())  # type: ignore[arg-type]
    host = cli._agent(build_parser().parse_args(["fix-loop", "--pr", "1"]), FakeGit())  # type: ignore[arg-type]

    assert contained.func is container.run_agent
    assert contained.keywords == {"model": "sonnet", "identity": ("Ada", "ada@example.test")}
    assert host.func is cli.run_claude_agent and host.keywords == {"model": "sonnet"}


def test_the_implement_plan_command_defaults_to_the_container_gate_the_host_agent_and_sonnet() -> None:
    from scripts.forge.cli import build_parser

    args = build_parser().parse_args(["implement-plan", "--plan", "plan/x.md"])

    assert args.model == "sonnet" and args.base == "develop"
    assert args.container is True and args.agent_container is False
    assert build_parser().parse_args(["implement-plan", "--plan", "x", "--no-container"]).container is False
    assert build_parser().parse_args(["implement-plan", "--plan", "x", "--container"]).container is True


@pytest.mark.parametrize(
    "argv",
    [
        ["ci-status"],
        ["implement-plan", "--plan", "x", "--author", "someone"],
        ["implement-plan", "--plan", "x", "--max-rounds", "2"],
        ["implement-plan", "--plan", "x", "--review-wait-minutes", "5"],
        ["fix-loop", "--pr", "1", "--author", "someone"],
    ],
)
def test_the_trimmed_operation_and_options_are_gone(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.forge.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)

    assert "error" in capsys.readouterr().err


def test_the_options_that_remain_on_the_owner_commands_still_parse() -> None:
    from scripts.forge.cli import build_parser

    plan = build_parser().parse_args(["implement-plan", "--plan", "x", "--wait-minutes", "7", "--no-fix"])
    loop = build_parser().parse_args(["fix-loop", "--pr", "1", "--max-rounds", "2", "--wait-minutes", "5"])

    assert plan.wait_minutes == 7 and plan.no_fix is True
    assert loop.max_rounds == 2 and loop.wait_minutes == 5


def test_the_fix_loop_command_defaults_to_sonnet() -> None:
    from scripts.forge.cli import build_parser

    assert build_parser().parse_args(["fix-loop", "--pr", "1"]).model == "sonnet"
    assert build_parser().parse_args(["fix-loop", "--pr", "1", "--model", "opus"]).model == "opus"


def test_a_denied_command_with_terminal_control_characters_is_listed_as_escapes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    command = chr(27) + "]52;c;ZXZpbA==" + chr(7) + "rm"
    denial = {"tool_name": "Bash", "tool_input": {"command": command}}
    result = {"is_error": False, "num_turns": 1, "duration_ms": 1, "permission_denials": [denial]}
    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(json.dumps(result)))

    local.run_claude_agent(TASK)

    err = capsys.readouterr().err
    assert chr(27) not in err and chr(7) not in err and "denied:" in err


def test_an_agent_error_message_with_control_characters_is_escaped_in_the_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = {"is_error": True, "result": chr(27) + "[2Jgone"}
    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(json.dumps(result), returncode=1))

    with pytest.raises(ForgeError) as raised:
        local.run_claude_agent(TASK)

    assert chr(27) not in str(raised.value) and "gone" in str(raised.value)


def test_each_denied_command_is_listed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    denial = {"tool_name": "Bash", "tool_input": {"command": "cp a b"}}
    result = {"is_error": False, "num_turns": 1, "duration_ms": 1, "permission_denials": [denial]}
    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: completed(json.dumps(result)))

    local.run_claude_agent(TASK)

    assert "denied: cp a b" in capsys.readouterr().err


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
        task = RoundTask("prompt", Path("old.md"), Path("new.md"), tmp_path)

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

        def run(
            command: list[str], cwd: Path, timeout: float, env: dict[str, str]
        ) -> subprocess.CompletedProcess[str]:
            seen.update(command=command, cwd=cwd, env=env)
            return completed("all good")

        monkeypatch.setattr(local, "run_bounded", run)

        passed, tail = local.run_gate("origin/develop", tmp_path)

        assert passed and tail == "all good"
        assert seen["command"] == [local.sys.executable, "-m", "scripts.run_checks", "pr", "--base", "origin/develop"]
        assert seen["cwd"] == tmp_path
        assert str(seen["env"]["PYTHONPATH"]).startswith(str(tmp_path / "src"))  # type: ignore[index]

    def test_a_failing_gate_reports_the_tail_of_its_output(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        output = "\n".join(f"line {number}" for number in range(40))
        monkeypatch.setattr(local, "run_bounded", lambda *a, **k: completed(output, returncode=1))

        passed, tail = local.run_gate("origin/develop", tmp_path)

        assert not passed and tail.splitlines() == [f"line {number}" for number in range(25, 40)]

    def test_a_gate_that_never_finishes_is_red(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        def slow(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("gate", 1)

        monkeypatch.setattr(local, "run_bounded", slow)

        assert local.run_gate("origin/develop", tmp_path) == (False, "The gate timed out.")

    def test_the_clones_source_shadows_an_installed_copy_when_the_gate_really_runs(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "scripts" / "run_checks.py").write_text(
            "import common\nprint(common.__file__)\nraise SystemExit(0)\n", encoding="utf-8"
        )
        (tmp_path / "src" / "common").mkdir(parents=True)
        (tmp_path / "src" / "common" / "__init__.py").write_text("", encoding="utf-8")

        passed, tail = local.run_gate("origin/develop", tmp_path)

        assert passed and str(tmp_path) in tail


class TestGateEnvironment:
    def test_the_gate_gets_the_scrubbed_environment_not_the_owners_secrets(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: dict[str, dict[str, str]] = {}

        def run(
            command: list[str], cwd: Path, timeout: float, env: dict[str, str]
        ) -> subprocess.CompletedProcess[str]:
            seen["env"] = env
            return completed("ok")

        monkeypatch.setattr(local, "run_bounded", run)
        monkeypatch.setenv("GH_TOKEN", "secret")
        monkeypatch.setenv("TRADING_RUNTIME_ALERT_SMTP_PASSWORD", "secret")

        local.run_gate("origin/develop", tmp_path)

        env = seen["env"]
        assert "GH_TOKEN" not in env and "TRADING_RUNTIME_ALERT_SMTP_PASSWORD" not in env
        assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["PYTHONPATH"].startswith(str(tmp_path / "src"))


class TestAgentEnvironmentScrubbedNames:
    def test_webhook_smtp_and_runtime_settings_do_not_reach_the_agent_or_the_gate(self, tmp_path: Path) -> None:
        base = {
            "PATH": "/bin",
            "TRADING_RUNTIME_ALERT_WEBHOOK_URL": "https://hooks.example.test/x",
            "TRADING_RUNTIME_ALERT_SMTP_HOST": "smtp.example.test",
            "SOME_WEBHOOK": "x",
            "HOME": "/home/owner",
        }

        env = local.agent_environment(base, tmp_path)

        assert set(env) & set(base) == {"PATH", "HOME"}


def test_importing_the_command_line_tool_does_not_import_the_trading_package() -> None:
    import sys

    code = "import sys; sys.modules['trading'] = None; import scripts.forge.cli; print('ok')"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(["src", "apps"])},
    )

    assert result.returncode == 0 and "ok" in result.stdout, result.stderr


class TestEmailFailures:
    @pytest.mark.parametrize(
        "error", [OSError("host smtp.example.test refused"), smtplib.SMTPAuthenticationError(535, b"bad")]
    )
    def test_a_network_or_smtp_failure_is_reported_without_its_message_and_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: Exception
    ) -> None:
        def broken(**_kwargs: object) -> bool:
            raise error

        monkeypatch.setattr(job_helpers, "resolve_email_config_from_env", lambda: object())
        monkeypatch.setattr(notifications, "notify_runtime_event", broken)

        local.email_notifier("subject", "message", {"outcome": "ready"})

        err = capsys.readouterr().err
        assert f"No email was sent: {type(error).__name__} while sending." in err
        assert "smtp.example.test" not in err and "bad" not in err

    def test_a_programming_error_is_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken() -> object:
            raise RuntimeError("a bug")

        monkeypatch.setattr(job_helpers, "resolve_email_config_from_env", broken)

        with pytest.raises(RuntimeError, match="a bug"):
            local.email_notifier("subject", "message", {"outcome": "ready"})


def test_the_controller_git_options_switch_off_hooks_and_fsmonitor() -> None:
    options = " ".join(local.NO_EXEC_GIT)

    assert "core.hooksPath=" in options and "core.fsmonitor=false" in options


def test_the_leftover_message_names_who_left_what_and_what_happens() -> None:
    from scripts.forge.sandbox import leftover_message

    text = leftover_message("The agent", "so nothing was pushed", [f"?? f{n}.txt" for n in range(8)])

    assert text.startswith("The agent left uncommitted changes in the sandbox, so nothing was pushed: ")
    assert "?? f4.txt" in text and "?? f5.txt" not in text
