"""Reporting service package.

This package is the stable public reporting surface. Concrete logic lives in
focused reporting modules beneath this package root.
"""

from trading.services.accounts import (
    GOAL_NOT_SET_TEXT,
    format_account_policy_text,
    format_goal_text,
)
from trading.services.evaluation import fetch_strategy_evaluation_for_account_row
from trading.services.reporting.calculations import (
    alpha_pct,
    benchmark_available,
    compute_market_value_and_unrealized,
    positions_summary_text,
    strategy_return_pct,
)
from trading.services.reporting.presentation import (
    account_report,
    compare_strategies,
    show_snapshots,
    snapshot_account,
)
from trading.services.reporting.stats import build_account_stats, infer_overall_trend
from trading.services.pricing import benchmark_stats, fetch_latest_prices

__all__ = [
    "GOAL_NOT_SET_TEXT",
    "account_report",
    "alpha_pct",
    "benchmark_available",
    "benchmark_stats",
    "build_account_stats",
    "compare_strategies",
    "compute_market_value_and_unrealized",
    "fetch_latest_prices",
    "fetch_strategy_evaluation_for_account_row",
    "format_account_policy_text",
    "format_goal_text",
    "infer_overall_trend",
    "positions_summary_text",
    "show_snapshots",
    "snapshot_account",
    "strategy_return_pct",
]
