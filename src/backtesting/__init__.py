"""Backtesting public facade.

This package is an explicit bounded context with internal layering
(`domain/services/repositories`) and stable convenience exports.
"""

from __future__ import annotations

from backtesting.backtest import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
    backtest_leaderboard,
    backtest_leaderboard_entries,
    backtest_report_full,
    run_backtest,
    run_backtest_batch,
)
from backtesting.models.report import (
    BacktestFullReport,
    BacktestLeaderboardEntry,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
)

__all__ = [
    "BacktestBatchConfig",
    "BacktestConfig",
    "BacktestResult",
    "backtest_leaderboard",
    "backtest_leaderboard_entries",
    "backtest_report_full",
    "run_backtest",
    "run_backtest_batch",
    "BacktestFullReport",
    "BacktestLeaderboardEntry",
    "BacktestReportSnapshot",
    "BacktestReportSummary",
    "BacktestReportTrade",
]
