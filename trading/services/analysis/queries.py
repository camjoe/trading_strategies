"""Analysis query flows for analysis consumers.

Owns read-only per-account performance analysis beneath the stable
``trading.services.analysis`` package surface.
"""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_float, row_expect_int, row_expect_str
from common.constants import SETTLEMENT_TICKER as _SETTLEMENT_TICKER
from trading.services.accounting import load_account_state
from trading.services.analysis.calculations import (
    TOP_POSITIONS_COUNT,
    compute_position_analysis,
    generate_improvement_notes,
)
from trading.services.reporting import (
    benchmark_stats,
    compute_market_value_and_unrealized,
    fetch_latest_prices,
    strategy_return_pct,
)


def fetch_account_analysis(
    conn: sqlite3.Connection,
    account_row: dict[str, object],
) -> dict[str, object]:
    """Return a full performance analysis dict for an account."""
    account_id = row_expect_int(account_row, "id")
    initial_cash = row_expect_float(account_row, "initial_cash")
    benchmark_ticker = row_expect_str(account_row, "benchmark_ticker")
    created_at = row_expect_str(account_row, "created_at")

    state = load_account_state(conn, account_id=account_id, initial_cash=initial_cash)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices(tickers) if tickers else {}
    market_value, unrealized = compute_market_value_and_unrealized(
        state.positions, state.avg_cost, prices
    )
    equity = state.cash + market_value

    effective_initial = initial_cash if initial_cash else state.total_deposited
    account_return = strategy_return_pct(equity, effective_initial) if effective_initial else 0.0
    _, bench_return = benchmark_stats(benchmark_ticker, effective_initial, created_at)
    alpha = (account_return - bench_return) if bench_return is not None else None

    position_analysis = compute_position_analysis(state, prices, equity)
    ranked = sorted(
        [
            position for position in position_analysis
            if float(position["marketPrice"]) > 0 and str(position["ticker"]) != _SETTLEMENT_TICKER
        ],
        key=lambda position: float(position["unrealizedPnlPct"]),
        reverse=True,
    )

    improvement_notes = generate_improvement_notes(
        account_return,
        bench_return,
        alpha,
        position_analysis,
        state.realized_pnl,
    )

    winners = ranked[:TOP_POSITIONS_COUNT]
    winner_tickers = {str(position["ticker"]) for position in winners}
    losers = list(
        reversed(
            [
                position for position in ranked
                if str(position["ticker"]) not in winner_tickers
            ][-TOP_POSITIONS_COUNT:]
        )
    )

    return {
        "accountReturnPct": account_return,
        "benchmarkReturnPct": bench_return,
        "benchmarkTicker": benchmark_ticker,
        "alphaPct": alpha,
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
