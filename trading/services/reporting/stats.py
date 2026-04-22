"""Reporting state and trend helpers for reporting consumers.

Owns service-level portfolio state loading and trend inference beneath the
stable ``trading.services.reporting`` package surface.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

from common.coercion import row_expect_float, row_expect_int, row_float
from trading.models import AccountRecord, AccountState
from trading.repositories.snapshots_repository import fetch_recent_equity_rows
from trading.services.accounting import load_account_state
from trading.services.reporting.calculations import compute_market_value_and_unrealized
from trading.services.reporting.market_data import fetch_latest_prices

# Trend inference needs at least two persisted points plus the current equity value.
MIN_TREND_HISTORY_POINTS = 3

# Trend inference always loads at least this many persisted rows to make a direction call.
MIN_TREND_LOOKBACK_ROWS = 2

# Equity moves inside this band are treated as flat for operator-facing trend summaries.
TREND_FLAT_BAND_PCT = 1.0


def _infer_overall_trend_impl(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
    *,
    fetch_recent_equity_rows_fn: Callable[..., list[dict[str, object]]],
    row_float_fn: Callable[..., float | None],
) -> str:
    rows = fetch_recent_equity_rows_fn(
        conn,
        account_id=account_id,
        limit=int(max(lookback, MIN_TREND_LOOKBACK_ROWS)),
    )
    history: list[float] = [h for h in (row_float_fn(r, "equity") for r in rows) if h is not None]
    history.reverse()
    history.append(current_equity)

    if len(history) < MIN_TREND_HISTORY_POINTS:
        return "insufficient-data"

    first = history[0]
    last = history[-1]
    if first == 0:
        return "insufficient-data"

    move_pct = ((last - first) / first) * 100.0
    if move_pct > TREND_FLAT_BAND_PCT:
        return "up"
    if move_pct < -TREND_FLAT_BAND_PCT:
        return "down"
    return "flat"


def build_account_stats(
    conn: sqlite3.Connection,
    account: AccountRecord,
) -> tuple[AccountState, dict[str, float], float, float, float]:
    account_id = row_expect_int(account, "id")
    initial_cash = row_expect_float(account, "initial_cash")
    state = load_account_state(conn, account_id=account_id, initial_cash=initial_cash)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices(tickers) if tickers else {}
    market_value, unrealized = compute_market_value_and_unrealized(state.positions, state.avg_cost, prices)
    equity = state.cash + market_value
    return state, prices, market_value, unrealized, equity


def infer_overall_trend(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
    *,
    fetch_recent_equity_rows_fn: Callable[..., list[dict[str, object]]] | None = None,
    row_float_fn: Callable[..., float | None] | None = None,
) -> str:
    return _infer_overall_trend_impl(
        conn,
        account_id,
        current_equity,
        lookback,
        fetch_recent_equity_rows_fn=fetch_recent_equity_rows_fn or fetch_recent_equity_rows,
        row_float_fn=row_float_fn or row_float,
    )


__all__ = [
    "build_account_stats",
    "infer_overall_trend",
]
