from __future__ import annotations

from types import SimpleNamespace


def make_backtest_args(**overrides):
    defaults = {
        "command": "backtest",
        "account": "acct1",
        "tickers_file": "src/infrastructure/config/trade_universe.txt",
        "universe_history_dir": None,
        "start": "2026-01-01",
        "end": "2026-03-01",
        "lookback_months": None,
        "slippage_bps": 5.0,
        "fee": 0.0,
        "run_name": None,
        "allow_approximate_leaps": False,
        "strategy": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_backtest_report_args(**overrides):
    defaults = {"command": "backtest-report", "run_id": 1}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_backtest_leaderboard_args(**overrides):
    defaults = {
        "command": "backtest-leaderboard",
        "limit": 10,
        "account": None,
        "strategy": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_backtest_batch_args(**overrides):
    defaults = {
        "command": "backtest-batch",
        "accounts": "acct1, acct2",
        "tickers_file": "src/infrastructure/config/trade_universe.txt",
        "universe_history_dir": None,
        "start": "2026-01-01",
        "end": "2026-03-01",
        "lookback_months": None,
        "slippage_bps": 5.0,
        "fee": 0.0,
        "run_name_prefix": None,
        "allow_approximate_leaps": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_backtest_result(**overrides):
    defaults = {
        "run_id": 1,
        "account_name": "acct1",
        "start_date": "2026-01-01",
        "end_date": "2026-03-01",
        "trade_count": 5,
        "ending_equity": 10500.0,
        "total_return_pct": 5.0,
        "max_drawdown_pct": -2.0,
        "benchmark_return_pct": 3.0,
        "alpha_pct": 2.0,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "calmar_ratio": None,
        "win_rate_pct": None,
        "profit_factor": None,
        "avg_trade_return_pct": None,
        "warnings": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


__all__ = [
    "make_backtest_args",
    "make_backtest_batch_args",
    "make_backtest_leaderboard_args",
    "make_backtest_report_args",
    "make_backtest_result",
]
