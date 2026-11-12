"""Pure ledger computation — no I/O, no repository calls."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from common.coercion import row_decimal, row_float
from common.constants import SETTLEMENT_TICKER
from trading.domain.accounting.holdings import Holdings
from trading.domain.accounting.validation import validate_order_values
from trading.models import AccountState
from trading.models.orders import Side


def normalize_trade_fields(trade: Mapping[str, object]) -> tuple[str, str, float, float, float]:
    """A trade row's ``(ticker, side, qty, price, fee)``, coerced and case-normalized.

    The backtest metrics replay computes in float and reads float REAL columns, so
    this returns float. The live account replay uses
    :func:`normalize_trade_fields_decimal` instead. An absent or unparseable numeric
    becomes ``0.0``; callers reject it on their own quantity and price rules, which
    differ (a $0 sell is valid for an expired option, a $0 buy never is).
    """
    return (
        str(trade["ticker"]).upper(),
        str(trade["side"]).lower(),
        row_float(trade, "qty") or 0.0,
        row_float(trade, "price") or 0.0,
        row_float(trade, "fee") or 0.0,
    )


def normalize_trade_fields_decimal(trade: Mapping[str, object]) -> tuple[str, str, Decimal, Decimal, Decimal]:
    """A trade row's ``(ticker, side, qty, price, fee)`` with exact ``Decimal`` numerics.

    The live account replay computes in ``Decimal``, so it reads the numeric fields
    as ``Decimal`` directly rather than through float. Absent or unparseable numerics
    become ``Decimal("0")``, matching :func:`normalize_trade_fields`.
    """
    return (
        str(trade["ticker"]).upper(),
        str(trade["side"]).lower(),
        row_decimal(trade, "qty") or Decimal("0"),
        row_decimal(trade, "price") or Decimal("0"),
        row_decimal(trade, "fee") or Decimal("0"),
    )


def _apply_trade_to_state(
    trade: dict[str, object],
    holdings: Holdings[Decimal],
    total_deposited: Decimal,
    settlement_ticker: str | None,
) -> Decimal:
    """Apply one trade to ``holdings`` and return the new ``total_deposited``."""
    ticker, side, qty, price, fee = normalize_trade_fields_decimal(trade)
    validate_order_values(side=side, qty=qty, price=price, noun="Trade")
    if settlement_ticker and ticker == settlement_ticker:
        # Settlement ticker buys are cash deposits (inflow); sells are withdrawals.
        if side == Side.BUY:
            deposit = qty * price
            holdings.cash += deposit
            return total_deposited + deposit
        if side == Side.SELL:
            holdings.cash -= qty * price + fee
            return total_deposited
    if side == Side.BUY:
        holdings.buy(ticker, qty, price, fee)
        return total_deposited
    if side == Side.SELL:
        holdings.sell(ticker, qty, price, fee)
        return total_deposited
    raise ValueError(f"Unsupported side: {side}")


def compute_account_state(
    initial_cash: Decimal,
    trades: list[dict[str, object]],
    settlement_ticker: str | None = SETTLEMENT_TICKER,
) -> AccountState:
    """Replay a trade list and return the resulting ``AccountState``.

    The replay computes in ``Decimal`` for exact money and quantity arithmetic.

    Parameters
    ----------
    initial_cash:
        Starting cash balance.  Set to ``Decimal("0")`` for accounts that seed
        capital exclusively through deposit trades (see ``settlement_ticker``).
    trades:
        Ordered list of trade rows from the ``trades`` table.  Each row must
        expose ``ticker``, ``side``, ``qty``, ``price``, and ``fee`` keys.
    settlement_ticker:
        Ticker reserved for cash deposits and withdrawals.  Defaults to
        :data:`SETTLEMENT_TICKER` (``"CASH"``).  A *buy* on this ticker adds
        ``qty * price`` to ``state.cash`` and ``state.total_deposited`` instead
        of creating a position; a *sell* subtracts the notional value from
        ``state.cash``.  Pass ``None`` to disable this behaviour and treat every
        ticker as a regular equity.
    """
    holdings = Holdings.starting_with(initial_cash)
    total_deposited = Decimal("0")
    for trade in trades:
        total_deposited = _apply_trade_to_state(trade, holdings, total_deposited, settlement_ticker)
    positions, avg_cost = holdings.open_positions()
    return AccountState(
        cash=holdings.cash,
        positions=positions,
        avg_cost=avg_cost,
        realized_pnl=holdings.realized_pnl,
        total_deposited=total_deposited,
    )
