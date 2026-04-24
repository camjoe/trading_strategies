from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from pathlib import Path


DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily_paper_trading"
DAILY_BACKTEST_REFRESH_MODULE = "trading.interfaces.runtime.jobs.daily_backtest_refresh"


def load_runtime_job(module_name: str):
    return importlib.import_module(module_name)


def load_daily_paper_trading():
    return load_runtime_job(DAILY_PAPER_TRADING_MODULE)


def load_daily_backtest_refresh():
    return load_runtime_job(DAILY_BACKTEST_REFRESH_MODULE)


daily_paper_trading = load_daily_paper_trading()
daily_backtest_refresh = load_daily_backtest_refresh()


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


def run_runtime_job_main(monkeypatch, tmp_path: Path, module_name: str, argv: list[str]) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [module_name.rsplit(".", 1)[-1]] + argv + ["--repo-root", str(tmp_path)],
    )
    (tmp_path / "local" / "logs").mkdir(parents=True, exist_ok=True)
    return load_runtime_job(module_name).main()


__all__ = [
    "DAILY_BACKTEST_REFRESH_MODULE",
    "DAILY_PAPER_TRADING_MODULE",
    "daily_backtest_refresh",
    "daily_paper_trading",
    "load_daily_backtest_refresh",
    "load_daily_paper_trading",
    "load_runtime_job",
    "make_daily_backtest_refresh_args",
    "run_runtime_job_main",
]
