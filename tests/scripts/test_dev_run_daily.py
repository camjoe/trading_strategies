from pathlib import Path

from scripts import dev_run_daily
from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import DEV_IGNORE_MARKET_HOURS_ENV
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_SMTP_HOST_ENV, RUNTIME_ALERT_WEBHOOK_ENV


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
