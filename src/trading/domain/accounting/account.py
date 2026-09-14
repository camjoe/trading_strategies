"""Pure ledger computation — no I/O, no repository calls."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal

from common.coercion import row_float
from common.constants import SETTLEMENT_TICKER
from trading.domain.accounting.ledger import Number, buy_position_delta, sell_position_delta
from trading.domain.accounting.validation import validate_order_values
from trading.models import AccountState


def normalize_trade_fields(trade: Mapping[str, object]) -> tuple[str, str, float, float, float]:
    """A trade row's ``(ticker, side, qty, price, fee)``, coerced and case-normalized.

    Shared with the backtest metrics replay so a persisted trade reads the same on
    both paths. An absent or unparseable numeric becomes ``0.0``; callers reject it
    on their own quantity and price rules, which differ (a $0 sell is valid for an
    expired option, a $0 buy never is).
    """
    return (
        str(trade["ticker"]).upper(),
        str(trade["side"]).lower(),
        row_float(trade, "qty") or 0.0,
        row_float(trade, "price") or 0.0,
        row_float(trade, "fee") or 0.0,
    )


def apply_buy(
    ticker: str,
    qty: Number,
    price: Number,
    fee: Number,
    positions: dict[str, Number],
    avg_cost: dict[str, Number],
    cash: Number,
) -> Number:
    """Apply a buy fill, returning the new cash balance.

    Raises the position and re-averages its cost **in place** in the caller's
    ``positions`` and ``avg_cost`` dicts. The fee is capitalized into the cost
    basis, so ``avg_cost`` is what the shares actually cost to acquire.

    Shared with the backtest (float) and the live replay (Decimal): the number
    type follows the caller's, and a fill costs the same on both paths. Quantities
    may be fractional; exact Decimal (or float in the backtest) arithmetic keeps a
    fully-sold position at exactly zero for ``_compact_positions``.
    """
    old_qty = positions[ticker]
    if old_qty + qty <= 0:
        raise ValueError(
            f"Buy of {qty} for {ticker} leaves a non-positive position ({old_qty + qty}); qty must be > 0."
        )
    delta = buy_position_delta(position_qty=old_qty, position_avg_cost=avg_cost[ticker], qty=qty, price=price, fee=fee)
    positions[ticker] = delta.ending_qty
    avg_cost[ticker] = delta.ending_avg_cost
    return cash + delta.cash_delta


def apply_sell(
    ticker: str,
    qty: Number,
    price: Number,
    fee: Number,
    positions: dict[str, Number],
    avg_cost: dict[str, Number],
    cash: Number,
    realized: Number,
) -> tuple[Number, Number]:
    """Apply a sell fill, returning the new ``(cash, realized)`` pair.

    Reduces the position **in place**. The fee is charged against realized P&L and
    netted out of proceeds, so a round trip is costed on both legs. Shared with the
    backtest (float) and the live replay (Decimal): the number type follows the caller's.
    """
    old_qty = positions[ticker]
    if qty > old_qty:
        raise ValueError(f"Invalid sell for {ticker}: trying to sell {qty}, holding {old_qty}.")
    delta = sell_position_delta(
        position_qty=old_qty, position_avg_cost=avg_cost[ticker], qty=qty, price=price, fee=fee
    )
    positions[ticker] = delta.ending_qty
    return cash + delta.cash_delta, realized + delta.realized_delta


def _compact_positions(
    positions: dict[str, Decimal], avg_cost: dict[str, Decimal]
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Drop sold-out positions, keeping the average cost of the ones still open.

    A closed position's stale ``avg_cost`` is dropped here rather than cleared on
    the sell: at zero quantity nothing reads it. Exact arithmetic (Decimal live,
    float in the backtest) over truncated quantities keeps a fully-sold position at
    exactly zero, so ``qty > 0`` is a reliable open-position test even for fractions.
    """
    open_positions = {ticker: qty for ticker, qty in positions.items() if qty > 0}
    open_avg_cost = {ticker: avg_cost[ticker] for ticker in open_positions}
    return open_positions, open_avg_cost


def _apply_trade_to_state(
    trade: dict[str, object],
    positions: dict[str, Decimal],
    avg_cost: dict[str, Decimal],
    cash: Decimal,
    realized: Decimal,
    total_deposited: Decimal,
    settlement_ticker: str | None,
) -> tuple[Decimal, Decimal, Decimal]:
    ticker, side, raw_qty, raw_price, raw_fee = normalize_trade_fields(trade)
    # The row parser reads storage floats; the replay computes in Decimal. str()
    # gives the clean decimal of the stored value, not the float's binary tail.
    qty = Decimal(str(raw_qty))
    price = Decimal(str(raw_price))
    fee = Decimal(str(raw_fee))
    validate_order_values(side=side, qty=qty, price=price, noun="Trade")
    if settlement_ticker and ticker == settlement_ticker:
        # Settlement ticker buys are cash deposits (inflow); sells are withdrawals.
        if side == "buy":
            deposit = qty * price
            return cash + deposit, realized, total_deposited + deposit
        if side == "sell":
            return cash - (qty * price + fee), realized, total_deposited
    if side == "buy":
        return apply_buy(ticker, qty, price, fee, positions, avg_cost, cash), realized, total_deposited
    if side == "sell":
        new_cash, new_realized = apply_sell(ticker, qty, price, fee, positions, avg_cost, cash, realized)
        return new_cash, new_realized, total_deposited
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
    positions: dict[str, Decimal] = defaultdict(Decimal)
    avg_cost: dict[str, Decimal] = defaultdict(Decimal)
    cash = initial_cash
    realized = Decimal("0")
    total_deposited = Decimal("0")
    for trade in trades:
        cash, realized, total_deposited = _apply_trade_to_state(
            trade, positions, avg_cost, cash, realized, total_deposited, settlement_ticker
        )
    positions, avg_cost = _compact_positions(positions, avg_cost)
    return AccountState(
        cash=cash,
        positions=positions,
        avg_cost=avg_cost,
        realized_pnl=realized,
        total_deposited=total_deposited,
    )
