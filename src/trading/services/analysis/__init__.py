"""Analysis service package.

This package is the stable public surface for read-only analytical computation:
per-account analysis, book performance windows, portfolio risk snapshots, the
cross-account exposure and concentration rollups, account/settlement portfolio
stats, and the live benchmark overlay. Concrete logic lives in focused modules
beneath this package root.
"""

from __future__ import annotations

from trading.services.analysis.benchmark import (
    attach_live_benchmark_summary,
    build_live_benchmark_overlay,
    fetch_benchmark_close_history,
)
from trading.services.analysis.concentration import fetch_portfolio_concentration
from trading.services.analysis.exposure import fetch_portfolio_exposure
from trading.services.analysis.performance import fetch_book_performance_window
from trading.services.analysis.portfolio import (
    build_account_stats,
    infer_overall_trend,
    inject_settlement_price,
    settlement_cash,
    settlement_corrected_equity,
)
from trading.services.analysis.queries import fetch_account_analysis
from trading.services.analysis.risk_snapshots import fetch_latest_risk_snapshot

__all__ = [
    "attach_live_benchmark_summary",
    "build_account_stats",
    "build_live_benchmark_overlay",
    "fetch_account_analysis",
    "fetch_benchmark_close_history",
    "fetch_book_performance_window",
    "fetch_latest_risk_snapshot",
    "fetch_portfolio_concentration",
    "fetch_portfolio_exposure",
    "infer_overall_trend",
    "inject_settlement_price",
    "settlement_cash",
    "settlement_corrected_equity",
]
