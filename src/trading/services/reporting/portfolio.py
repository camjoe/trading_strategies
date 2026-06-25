"""Reporting state and trend helpers for reporting consumers.

Owns service-level portfolio state loading and trend inference beneath the
stable ``trading.services.reporting`` package surface.
"""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_float, row_expect_int
from common.constants import SETTLEMENT_TICKER
from trading.models import AccountRecord, AccountState
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounting import load_account_state
from trading.services.market_data import MarketDataProvider
from trading.services.reporting.math import compute_market_value_and_unrealized
from trading.services.pricing import fetch_latest_prices

# The settlement ticker is always worth exactly $1 per unit (it represents cash).
_SETTLEMENT_PRICE = 1.0

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
) -> str:
    history = EquitySnapshotRepository(conn).fetch_recent_equity(
        account_id=account_id,
        limit=int(max(lookback, MIN_TREND_LOOKBACK_ROWS)),
    )
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


def settlement_corrected_equity(state: object, prices: object) -> float:
    """Total equity including the settlement position (cash-equivalent ticker).

    The settlement ticker represents cash held as a position; it must be
    priced at ``_SETTLEMENT_PRICE`` before calling this function (see
    ``inject_settlement_price``).
    """
    from trading.models.account_state import AccountState

    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return 0.0
    return state.cash + sum(state.positions.get(t, 0.0) * prices.get(t, 0.0) for t in state.positions)


def inject_settlement_price(state: object, prices: object) -> None:
    """Ensure the settlement ticker has a price entry so equity math is correct.

    When an account holds the settlement ticker as a position it must be
    valued at exactly ``_SETTLEMENT_PRICE`` (one dollar per unit).  This
    function inserts that price only if it is missing, and only when the
    state actually holds a settlement position.
    """
    from trading.models.account_state import AccountState

    if not isinstance(state, AccountState) or not isinstance(prices, dict):
        return
    if SETTLEMENT_TICKER in state.positions and SETTLEMENT_TICKER not in prices:
        prices[SETTLEMENT_TICKER] = _SETTLEMENT_PRICE


def settlement_cash(state: object, prices: object) -> float:
    """Return the cash component of an account state, or 0 if state is missing."""
    from trading.models.account_state import AccountState

    if not isinstance(state, AccountState):
        return 0.0
    return state.cash


def build_account_stats(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    provider: MarketDataProvider | None = None,
) -> tuple[AccountState, dict[str, float], float, float, float]:
    account_id = row_expect_int(account, "id")
    initial_cash = row_expect_float(account, "initial_cash")
    state = load_account_state(conn, account_id=account_id, initial_cash=initial_cash)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices(tickers, provider=provider) if tickers else {}
    market_value, unrealized = compute_market_value_and_unrealized(state.positions, state.avg_cost, prices)
    equity = state.cash + market_value
    return state, prices, market_value, unrealized, equity


def infer_overall_trend(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
) -> str:
    return _infer_overall_trend_impl(
        conn,
        account_id,
        current_equity,
        lookback,
    )


__all__ = [
    "build_account_stats",
    "infer_overall_trend",
    "inject_settlement_price",
    "settlement_cash",
    "settlement_corrected_equity",
]
