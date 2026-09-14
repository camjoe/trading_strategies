"""Pure book-fill accounting — builds a ``BookFillTransition``, no I/O."""

from __future__ import annotations

from decimal import Decimal

from trading.domain.accounting.ledger import buy_position_delta, sell_position_delta
from trading.domain.accounting.validation import normalize_order_input, validate_order_values
from trading.models.books import BookFillTransition


def _compute_slippage_amount(
    *,
    side: str,
    qty: Decimal,
    fill_price: Decimal,
    requested_price: Decimal | None,
) -> Decimal:
    """Fill cost versus the requested price, signed so positive is worse for the book.

    A buy filled above request or a sell filled below it is positive slippage. No
    requested price means slippage is not measurable, so return ``Decimal("0")``.
    """
    if requested_price is None:
        return Decimal("0")
    expected_notional = requested_price * qty
    actual_notional = fill_price * qty
    if side == "buy":
        return actual_notional - expected_notional
    return expected_notional - actual_notional


def apply_book_fill_transition(
    *,
    side: str,
    symbol: str,
    qty: Decimal,
    fill_price: Decimal,
    commission: Decimal,
    requested_price: Decimal | None,
    position_qty: Decimal,
    position_avg_cost: Decimal,
    cash: Decimal,
    realized_pnl: Decimal,
) -> BookFillTransition:
    normalized_side, normalized_symbol = normalize_order_input(side, symbol, require_symbol=True)

    validate_order_values(
        side=normalized_side,
        qty=qty,
        price=fill_price,
        commission=commission,
        noun="Fill",
    )
    if normalized_side == "sell" and qty > position_qty:
        raise ValueError(f"Invalid sell for {normalized_symbol}: trying to sell {qty}, holding {position_qty}.")

    if normalized_side == "buy":
        buy = buy_position_delta(
            position_qty=position_qty,
            position_avg_cost=position_avg_cost,
            qty=qty,
            price=fill_price,
            fee=commission,
        )
        ending_qty = buy.ending_qty
        ending_avg_cost = buy.ending_avg_cost
        cash_delta = buy.cash_delta
        realized_pnl_delta = Decimal("0")
    else:
        sell = sell_position_delta(
            position_qty=position_qty,
            position_avg_cost=position_avg_cost,
            qty=qty,
            price=fill_price,
            fee=commission,
        )
        ending_qty = sell.ending_qty
        # A fully closed position resets its average cost; a partial sell keeps it.
        ending_avg_cost = Decimal("0") if ending_qty == 0 else position_avg_cost
        cash_delta = sell.cash_delta
        realized_pnl_delta = sell.realized_delta

    ending_cash = cash + cash_delta
    ending_realized_pnl = realized_pnl + realized_pnl_delta
    ending_market_value = ending_qty * fill_price
    ending_unrealized_pnl = ending_market_value - (ending_qty * ending_avg_cost)
    ending_equity = ending_cash + ending_market_value

    return BookFillTransition(
        symbol=normalized_symbol,
        side=normalized_side,
        qty=qty,
        fill_price=fill_price,
        commission=commission,
        requested_price=requested_price,
        cash_delta=cash_delta,
        realized_pnl_delta=realized_pnl_delta,
        slippage_amount=_compute_slippage_amount(
            side=normalized_side,
            qty=qty,
            fill_price=fill_price,
            requested_price=requested_price,
        ),
        ending_qty=ending_qty,
        ending_avg_cost=ending_avg_cost,
        ending_cash=ending_cash,
        ending_realized_pnl=ending_realized_pnl,
        ending_market_value=ending_market_value,
        ending_unrealized_pnl=ending_unrealized_pnl,
        ending_equity=ending_equity,
    )
