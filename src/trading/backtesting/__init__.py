"""Backtesting public facade.

This package is an explicit bounded context with internal layering
(`domain/services/repositories`) and stable convenience exports.
"""

from __future__ import annotations

from trading.backtesting.backtest import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
    WalkForwardConfig,
    WalkForwardSummary,
    backtest_leaderboard,
    backtest_leaderboard_entries,
    backtest_report,
    backtest_report_full,
    backtest_report_summary,
    build_walk_forward_windows,
    run_backtest,
    run_backtest_batch,
    run_walk_forward_backtest,
    walk_forward_report,
)
from trading.backtesting.report_models import (
    BacktestFullReport,
    BacktestLeaderboardEntry,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
    WalkForwardDetailReport,
    WalkForwardWindowDetail,
)

__all__ = [
    "BacktestBatchConfig",
    "BacktestConfig",
    "BacktestResult",
    "backtest_leaderboard",
    "backtest_leaderboard_entries",
    "WalkForwardConfig",
    "WalkForwardSummary",
    "backtest_report_full",
    "backtest_report",
    "backtest_report_summary",
    "build_walk_forward_windows",
    "run_backtest",
    "run_backtest_batch",
    "walk_forward_report",
    "run_walk_forward_backtest",
    "BacktestFullReport",
    "BacktestLeaderboardEntry",
    "BacktestReportSnapshot",
    "BacktestReportSummary",
    "BacktestReportTrade",
    "WalkForwardDetailReport",
    "WalkForwardWindowDetail",
]
