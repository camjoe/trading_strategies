"""Analysis query flows for analysis consumers.

Owns read-only per-account performance analysis beneath the stable
``trading.services.analysis`` package surface.
"""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_str
from common.constants import SETTLEMENT_TICKER
from trading.models import AccountRecord
from trading.services.analysis.portfolio import build_account_return_summary, build_account_stats
from trading.services.analysis.position import (
    TOP_POSITIONS_COUNT,
    compute_position_analysis,
    generate_improvement_notes,
)
from trading.services.market_data.protocols import MarketDataProvider


def fetch_account_analysis(
    conn: sqlite3.Connection,
    account_row: AccountRecord,
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, object]:
    """Return a full performance analysis dict for an account."""
    benchmark_ticker = row_expect_str(account_row, "benchmark_ticker")
    state, prices, _market_value, unrealized, equity = build_account_stats(conn, account_row, provider=provider)
    summary = build_account_return_summary(account_row, state, equity, provider=provider)

    position_analysis = compute_position_analysis(state, prices, equity)
    ranked = sorted(
        [
            position
            for position in position_analysis
            if float(position["marketPrice"]) > 0 and str(position["ticker"]) != SETTLEMENT_TICKER
        ],
        key=lambda position: float(position["unrealizedPnlPct"]),
        reverse=True,
    )

    improvement_notes = generate_improvement_notes(
        summary.account_return_pct,
        summary.benchmark_return_pct,
        summary.alpha_pct,
        position_analysis,
        state.realized_pnl,
    )

    winners = ranked[:TOP_POSITIONS_COUNT]
    # The worst performers, worst first, taken from everything below the winners.
    # Slicing by position keeps winners and losers from overlapping when there are
    # fewer than 2*TOP_POSITIONS_COUNT names.
    losers = list(reversed(ranked[TOP_POSITIONS_COUNT:][-TOP_POSITIONS_COUNT:]))

    return {
        "accountReturnPct": summary.account_return_pct,
        "benchmarkReturnPct": summary.benchmark_return_pct,
        "benchmarkTicker": benchmark_ticker,
        "alphaPct": summary.alpha_pct,
        "realizedPnl": state.realized_pnl,
        "unrealizedPnl": unrealized,
        "equity": equity,
        "topWinners": winners,
        "topLosers": losers,
        "improvementNotes": improvement_notes,
    }


__all__ = [
    "fetch_account_analysis",
]
