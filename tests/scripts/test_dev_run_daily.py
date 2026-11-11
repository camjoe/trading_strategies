import datetime as dt
from pathlib import Path

from common.runtime_job_status import DAILY_PAPER_TRADING_COMPLETE_SENTINEL
from scripts import dev_run_daily
from trading.interfaces.runtime.jobs.daily.paper_trading import already_completed_today
from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import DEV_IGNORE_MARKET_HOURS_ENV
from trading.interfaces.runtime.jobs.job_helpers import (
    RUNTIME_ALERT_SMTP_HOST_ENV,
    RUNTIME_ALERT_WEBHOOK_ENV,
    logs_dir_for_repo,
)


def test_job_environment_points_at_the_sandbox_with_notifications_off(monkeypatch) -> None:
    monkeypatch.setenv(RUNTIME_ALERT_WEBHOOK_ENV, "https://example.invalid/hook")
    monkeypatch.setenv(RUNTIME_ALERT_SMTP_HOST_ENV, "smtp.example.invalid")
    monkeypatch.setenv(DEV_IGNORE_MARKET_HOURS_ENV, "1")
    database_path = Path("local") / "sandbox.db"

    env = dev_run_daily.build_job_environment(database_path, ignore_market_hours=False)

    assert env["TRADING_DB_PATH"] == str(database_path)
    assert env["TRADING_MARKET_DATA_PROVIDER"] == "demo"
    assert env["TRADING_EXTERNAL_FEATURES_DISABLED"] == "1"
    assert RUNTIME_ALERT_WEBHOOK_ENV not in env
    assert RUNTIME_ALERT_SMTP_HOST_ENV not in env
    assert DEV_IGNORE_MARKET_HOURS_ENV not in env


def test_job_environment_sets_the_market_hours_override_on_request() -> None:
    env = dev_run_daily.build_job_environment(Path("sandbox.db"), ignore_market_hours=True)

    assert env[DEV_IGNORE_MARKET_HOURS_ENV] == "1"


def test_job_command_points_the_run_at_the_dev_root(tmp_path) -> None:
    command = dev_run_daily.build_job_command(tmp_path, ["--accounts", "sandbox_core"])

    assert command[command.index("--repo-root") + 1] == str(tmp_path / "local" / "dev_runs")
    assert command[-2:] == ["--accounts", "sandbox_core"]


def test_a_completed_dev_run_does_not_make_the_scheduled_run_skip(tmp_path) -> None:
    today = dt.date(2026, 11, 9)
    dev_logs = logs_dir_for_repo(dev_run_daily.dev_run_root(tmp_path))
    dev_logs.mkdir(parents=True)
    (dev_logs / "daily_paper_trading_20261109_093000.log").write_text(
        f"{DAILY_PAPER_TRADING_COMPLETE_SENTINEL}\n", encoding="utf-8"
    )

    assert already_completed_today(dev_logs, today=today) is True
    assert already_completed_today(logs_dir_for_repo(tmp_path), today=today) is False
