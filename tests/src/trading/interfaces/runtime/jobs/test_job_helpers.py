from __future__ import annotations

import os
from pathlib import Path

from trading.interfaces.runtime.jobs.job_helpers import (
    RUNTIME_ALERT_SMTP_FROM_ENV,
    RUNTIME_ALERT_SMTP_HOST_ENV,
    RUNTIME_ALERT_SMTP_PASSWORD_ENV,
    RUNTIME_ALERT_SMTP_PORT_ENV,
    RUNTIME_ALERT_SMTP_TO_ENV,
    RUNTIME_ALERT_SMTP_USERNAME_ENV,
    RUNTIME_ALERT_SMTP_USE_TLS_ENV,
    already_completed_for_period,
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    resolve_accounts,
    resolve_email_config_from_env,
    run_command,
    skip_if_already_completed_for_period,
    stream_command,
    tee_line,
)

_ALL_SMTP_ENV = (
    RUNTIME_ALERT_SMTP_HOST_ENV,
    RUNTIME_ALERT_SMTP_PORT_ENV,
    RUNTIME_ALERT_SMTP_USERNAME_ENV,
    RUNTIME_ALERT_SMTP_PASSWORD_ENV,
    RUNTIME_ALERT_SMTP_FROM_ENV,
    RUNTIME_ALERT_SMTP_TO_ENV,
    RUNTIME_ALERT_SMTP_USE_TLS_ENV,
)


def _clear_smtp_env(monkeypatch) -> None:
    for name in _ALL_SMTP_ENV:
        monkeypatch.delenv(name, raising=False)


def test_resolve_email_config_returns_none_when_unconfigured(monkeypatch):
    _clear_smtp_env(monkeypatch)
    assert resolve_email_config_from_env() is None


def test_resolve_email_config_requires_host_sender_and_recipient(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_HOST_ENV, "smtp.test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_FROM_ENV, "alerts@test")
    # No recipients -> not deliverable -> None.
    assert resolve_email_config_from_env() is None


def test_resolve_email_config_builds_from_env_with_defaults(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_HOST_ENV, "smtp.test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_FROM_ENV, "alerts@test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_TO_ENV, "ops@test, oncall@test")

    config = resolve_email_config_from_env()

    assert config is not None
    assert config.host == "smtp.test"
    assert config.sender == "alerts@test"
    assert config.recipients == ("ops@test", "oncall@test")
    assert config.port == 587  # default STARTTLS submission port
    assert config.use_tls is True
    assert config.username is None
    assert config.password is None


def test_resolve_email_config_reads_auth_port_and_tls_toggle(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_HOST_ENV, "smtp.test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_FROM_ENV, "alerts@test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_TO_ENV, "ops@test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_USERNAME_ENV, "user")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_PASSWORD_ENV, "secret")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_PORT_ENV, "2525")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_USE_TLS_ENV, "false")

    config = resolve_email_config_from_env()

    assert config is not None
    assert (config.username, config.password) == ("user", "secret")
    assert config.port == 2525
    assert config.use_tls is False


def test_resolve_email_config_falls_back_to_default_port_on_bad_value(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_HOST_ENV, "smtp.test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_FROM_ENV, "alerts@test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_TO_ENV, "ops@test")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_PORT_ENV, "not-a-number")

    config = resolve_email_config_from_env()

    assert config is not None
    assert config.port == 587


def test_logs_dir_for_repo_uses_local_logs(tmp_path: Path):
    assert logs_dir_for_repo(tmp_path) == tmp_path / "local" / "logs"


def test_tee_line_appends_and_prints(tmp_path: Path, capsys):
    log_path = tmp_path / "task.log"

    tee_line(log_path, "hello")

    captured = capsys.readouterr()
    assert captured.out == "hello\n"
    assert log_path.read_text(encoding="utf-8") == "hello\n"


def test_latest_log_contains_sentinel_uses_newest_match(tmp_path: Path):
    older = tmp_path / "job_older.log"
    newer = tmp_path / "job_newer.log"
    older.write_text("COMPLETE\n", encoding="utf-8")
    newer.write_text("incomplete\n", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert latest_log_contains_sentinel(tmp_path, "job_*.log", "COMPLETE") is False


def test_already_completed_for_period_checks_older_completed_logs(tmp_path: Path):
    completed = tmp_path / "job_2026_06_20260601_000000.log"
    current = tmp_path / "job_2026_06_20260629_120000.log"
    completed.write_text("COMPLETE\n", encoding="utf-8")
    current.write_text("RUN META\n", encoding="utf-8")

    assert (
        already_completed_for_period(
            log_dir=tmp_path,
            job_name="job",
            period_tag="2026_06",
            sentinel="COMPLETE",
        )
        is True
    )


def test_latest_log_contains_sentinel_returns_false_without_matches(tmp_path: Path):
    assert latest_log_contains_sentinel(tmp_path, "missing_*.log", "COMPLETE") is False


def test_run_command_returns_exit_code_and_output(tmp_path: Path):
    log_path = tmp_path / "run.log"
    exit_code, output = run_command(
        log_path,
        "echo-test",
        ["-c", "print('hello from subprocess')"],
        tmp_path,
    )
    assert exit_code == 0
    assert "hello from subprocess" in output
    log_text = log_path.read_text(encoding="utf-8")
    assert "START: echo-test" in log_text
    assert "DONE: echo-test" in log_text


def test_run_command_captures_nonzero_exit(tmp_path: Path):
    log_path = tmp_path / "run.log"
    exit_code, output = run_command(
        log_path,
        "failing-step",
        ["-c", "import sys; sys.exit(2)"],
        tmp_path,
    )
    assert exit_code == 2
    assert "ERROR: failing-step" in log_path.read_text(encoding="utf-8")


def test_stream_command_raises_on_nonzero(tmp_path: Path):
    import pytest

    log_path = tmp_path / "run.log"
    with pytest.raises(RuntimeError, match="Step failed: bad-step"):
        stream_command(
            log_path,
            "bad-step",
            ["-c", "import sys; sys.exit(1)"],
            tmp_path,
        )


def test_stream_command_succeeds_silently(tmp_path: Path):
    log_path = tmp_path / "run.log"
    stream_command(
        log_path,
        "ok-step",
        ["-c", "print('output')"],
        tmp_path,
    )
    log_text = log_path.read_text(encoding="utf-8")
    assert "DONE: ok-step" in log_text


def test_resolve_accounts_returns_all_for_all_keyword() -> None:
    assert resolve_accounts("all", ["acct_a", "acct_b"]) == ["acct_a", "acct_b"]


def test_resolve_accounts_parses_comma_separated_values() -> None:
    assert resolve_accounts("acct_a, acct_b", ["acct_a", "acct_b", "acct_c"]) == ["acct_a", "acct_b"]


def test_resolve_accounts_rejects_unknown_accounts() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unknown account\\(s\\): ghost"):
        resolve_accounts("ghost", ["acct_a"])


def test_skip_if_already_completed_for_period_returns_false_without_matching_log(tmp_path: Path, capsys):
    log_path = tmp_path / "task.log"

    skipped = skip_if_already_completed_for_period(
        log_path=log_path,
        log_dir=tmp_path,
        job_name="job",
        period_name="day",
        period_tag="20260520",
        sentinel="COMPLETE",
        force_run=False,
    )

    assert skipped is False
    assert capsys.readouterr().out == ""


def test_latest_log_contains_sentinel_returns_false_when_latest_read_fails(monkeypatch, tmp_path: Path):
    log = tmp_path / "job_latest.log"
    log.write_text("COMPLETE\n", encoding="utf-8")
    original_read_text = Path.read_text

    def _broken_read_text(self, *args, **kwargs):
        if self == log:
            raise OSError("boom")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _broken_read_text)

    assert latest_log_contains_sentinel(tmp_path, "job_*.log", "COMPLETE") is False
