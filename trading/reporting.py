# Architecture: compatibility shim — import from trading.services.reporting_service instead.
from trading.services.accounts_service import format_goal_text
from trading.services.reporting_service import (
    account_report,
    alpha_pct,
    benchmark_available,
    benchmark_stats,
    build_account_stats,
    compare_strategies,
    compute_market_value_and_unrealized,
    fetch_latest_prices,
    infer_overall_trend,
    positions_summary_text,
    show_snapshots,
    snapshot_account,
    strategy_return_pct,
    utc_now_iso,
)

__all__ = [
    "account_report",
    "alpha_pct",
    "benchmark_available",
    "benchmark_stats",
    "build_account_stats",
    "compare_strategies",
    "compute_market_value_and_unrealized",
    "fetch_latest_prices",
    "format_goal_text",
    "infer_overall_trend",
    "positions_summary_text",
    "show_snapshots",
    "snapshot_account",
    "strategy_return_pct",
    "utc_now_iso",
]
