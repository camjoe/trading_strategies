from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from pathlib import Path


DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily_paper_trading"
DAILY_BACKTEST_REFRESH_MODULE = "trading.interfaces.runtime.jobs.daily_backtest_refresh"
CHECK_DAILY_TRADER_HEALTH_MODULE = "trading.interfaces.runtime.jobs.check_daily_trader_health"
MANAGE_JOB_SCHEDULES_MODULE = "trading.interfaces.runtime.jobs.manage_job_schedules"
DAILY_SNAPSHOT_MODULE = "trading.interfaces.runtime.jobs.daily_snapshot"
RUN_AUTO_TRADES_MODULE = "trading.interfaces.runtime.jobs.run_auto_trades"
DAILY_CHALLENGER_SHADOW_EVAL_MODULE = "trading.interfaces.runtime.jobs.daily_challenger_shadow_eval"


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


def load_daily_snapshot():
    return load_runtime_job(DAILY_SNAPSHOT_MODULE)


def load_run_auto_trades():
    return load_runtime_job(RUN_AUTO_TRADES_MODULE)


def load_daily_challenger_shadow_eval():
    return load_runtime_job(DAILY_CHALLENGER_SHADOW_EVAL_MODULE)


daily_paper_trading = load_daily_paper_trading()
daily_backtest_refresh = load_daily_backtest_refresh()
check_daily_trader_health = load_check_daily_trader_health()
manage_job_schedules = load_manage_job_schedules()
daily_snapshot = load_daily_snapshot()
run_auto_trades = load_run_auto_trades()
daily_challenger_shadow_eval = load_daily_challenger_shadow_eval()


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
        "daily_challenger_shadow_eval_time": "",
        "daily_challenger_shadow_eval_task_name": r"Trading\DailyChallengerShadowEval",
        "enable_daily_challenger_shadow_eval": False,
        "auto_shadow_eval_from_daily_paper": False,
        "shadow_eval_lead_minutes": 20,
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


def make_daily_snapshot_args(**overrides):
    defaults = {
        "accounts": "all",
        "force_run": False,
        "run_source": "test-run",
        "enable_run": True,
        "max_attempts": 2,
        "backoff_seconds": 0.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_run_auto_trades_args(**overrides):
    defaults = {
        "min_trades": 1,
        "max_trades": 1,
        "seed": None,
        "accounts": "acct1",
        "tickers_file": "trading/config/trade_universe.txt",
        "fee": 0.0,
        "execution_mode": "account",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_daily_challenger_shadow_eval_args(**overrides):
    defaults = {
        "accounts": "all",
        "force_run": False,
        "run_source": "test-run",
        "enable_run": True,
        "rolling_window_days": 30,
        "repo_root": ".",
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
    "DAILY_SNAPSHOT_MODULE",
    "MANAGE_JOB_SCHEDULES_MODULE",
    "DAILY_BACKTEST_REFRESH_MODULE",
    "DAILY_PAPER_TRADING_MODULE",
    "RUN_AUTO_TRADES_MODULE",
    "DAILY_CHALLENGER_SHADOW_EVAL_MODULE",
    "check_daily_trader_health",
    "daily_snapshot",
    "manage_job_schedules",
    "daily_backtest_refresh",
    "daily_paper_trading",
    "run_auto_trades",
    "daily_challenger_shadow_eval",
    "load_check_daily_trader_health",
    "load_daily_snapshot",
    "load_manage_job_schedules",
    "load_daily_backtest_refresh",
    "load_daily_paper_trading",
    "load_run_auto_trades",
    "load_daily_challenger_shadow_eval",
    "load_runtime_job",
    "make_daily_backtest_refresh_args",
    "make_daily_snapshot_args",
    "make_daily_challenger_shadow_eval_args",
    "make_manage_job_schedules_args",
    "make_run_auto_trades_args",
    "run_runtime_job_main",
]
