"""Backtesting public facade.

This package is an explicit bounded context with internal layering
(`domain/services/repositories`) and stable convenience exports.
"""

from __future__ import annotations

from trading.backtesting.backtest import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
    backtest_leaderboard,
    backtest_leaderboard_entries,
    backtest_report,
    backtest_report_full,
    backtest_report_summary,
    run_backtest,
    run_backtest_batch,
)
from trading.backtesting.report_models import (
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
    "backtest_report",
    "backtest_report_summary",
    "run_backtest",
    "run_backtest_batch",
    "BacktestFullReport",
    "BacktestLeaderboardEntry",
    "BacktestReportSnapshot",
    "BacktestReportSummary",
    "BacktestReportTrade",
]
