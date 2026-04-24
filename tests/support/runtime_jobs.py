from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from pathlib import Path


DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily_paper_trading"
DAILY_BACKTEST_REFRESH_MODULE = "trading.interfaces.runtime.jobs.daily_backtest_refresh"
CHECK_DAILY_TRADER_HEALTH_MODULE = "trading.interfaces.runtime.jobs.check_daily_trader_health"
MANAGE_JOB_SCHEDULES_MODULE = "trading.interfaces.runtime.jobs.manage_job_schedules"


def load_runtime_job(module_name: str):
    return importlib.import_module(module_name)


def load_daily_paper_trading():
    return load_runtime_job(DAILY_PAPER_TRADING_MODULE)


def load_daily_backtest_refresh():
    return load_runtime_job(DAILY_BACKTEST_REFRESH_MODULE)


def load_check_daily_trader_health():
    return load_runtime_job(CHECK_DAILY_TRADER_HEALTH_MODULE)


def load_manage_job_schedules():
    return load_runtime_job(MANAGE_JOB_SCHEDULES_MODULE)


daily_paper_trading = load_daily_paper_trading()
daily_backtest_refresh = load_daily_backtest_refresh()
check_daily_trader_health = load_check_daily_trader_health()
manage_job_schedules = load_manage_job_schedules()


def make_daily_backtest_refresh_args(**overrides):
    defaults = {
        "accounts": "all",
        "force_run": False,
        "run_source": "test-run",
        "enable_run": True,
        "max_attempts": 2,
        "backoff_seconds": 0.0,
        "tickers_file": "tickers.txt",
        "universe_history_dir": None,
        "start": None,
        "end": None,
        "lookback_months": 6,
        "slippage_bps": 5.0,
        "fee": 0.0,
        "run_name_prefix": "daily_backtest_refresh",
        "allow_approximate_leaps": False,
        "repo_root": ".",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_manage_job_schedules_args(**overrides):
    defaults = {
        "daily_paper_trading_time": "",
        "daily_paper_trading_task_name": r"Trading\DailyPaperTrading",
        "daily_paper_trading_fallback_time": "",
        "daily_paper_trading_fallback_task_name": r"Trading\DailyPaperTradingFallback",
        "daily_snapshot_time": "",
        "daily_snapshot_task_name": r"Trading\DailySnapshot",
        "enable_daily_snapshot": False,
        "daily_backtest_refresh_time": "",
        "daily_backtest_refresh_task_name": r"Trading\DailyBacktestRefresh",
        "enable_daily_backtest_refresh": False,
        "health_check_time": "",
        "health_check_task_name": r"Trading\DailyTraderHealthCheck",
        "health_check_max_age_hours": 24.0,
        "weekly_db_backup_time": "",
        "weekly_db_backup_day_of_week": "Sunday",
        "weekly_db_backup_task_name": r"Trading\WeeklyDbBackup",
        "unregister": False,
        "dry_run": False,
        "python": "/tmp/.venv/bin/python",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def run_runtime_job_main(monkeypatch, tmp_path: Path, module_name: str, argv: list[str]) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [module_name.rsplit(".", 1)[-1]] + argv + ["--repo-root", str(tmp_path)],
    )
    (tmp_path / "local" / "logs").mkdir(parents=True, exist_ok=True)
    return load_runtime_job(module_name).main()


__all__ = [
    "CHECK_DAILY_TRADER_HEALTH_MODULE",
    "MANAGE_JOB_SCHEDULES_MODULE",
    "DAILY_BACKTEST_REFRESH_MODULE",
    "DAILY_PAPER_TRADING_MODULE",
    "check_daily_trader_health",
    "manage_job_schedules",
    "daily_backtest_refresh",
    "daily_paper_trading",
    "load_check_daily_trader_health",
    "load_manage_job_schedules",
    "load_daily_backtest_refresh",
    "load_daily_paper_trading",
    "load_runtime_job",
    "make_daily_backtest_refresh_args",
    "make_manage_job_schedules_args",
    "run_runtime_job_main",
]
