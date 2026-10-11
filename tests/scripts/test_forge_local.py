import json
import subprocess
from pathlib import Path

import pytest

from scripts.forge import local
from scripts.forge.base import ForgeError
from scripts.forge.fix_loop import RoundTask

TASK = RoundTask(7, "origin/develop", "prompt", Path("old.md"), Path("new.md"))


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
        return seen[0]

    def test_the_model_is_passed_to_claude(self, monkeypatch: pytest.MonkeyPatch) -> None:
        command = self._command_for(monkeypatch, model="sonnet")

        assert command[command.index("--model") + 1] == "sonnet"

    def test_without_a_model_claude_uses_its_own_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert "--model" not in self._command_for(monkeypatch)


def test_the_fix_loop_command_defaults_to_sonnet() -> None:
    from scripts.forge.cli import build_parser

    assert build_parser().parse_args(["fix-loop", "--pr", "1"]).model == "sonnet"
    assert build_parser().parse_args(["fix-loop", "--pr", "1", "--model", "opus"]).model == "opus"
