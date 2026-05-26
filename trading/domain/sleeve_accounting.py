from __future__ import annotations

from dataclasses import dataclass


# Supported order directions for sleeve fills.
VALID_FILL_SIDES = {"buy", "sell"}


@dataclass(frozen=True, slots=True)
class SleeveFillTransition:
    symbol: str
    side: str
    qty: float
    fill_price: float
    commission: float
    requested_price: float | None
    cash_delta: float
    realized_pnl_delta: float
    slippage_amount: float
    ending_qty: float
    ending_avg_cost: float
    ending_cash: float
    ending_realized_pnl: float
    ending_market_value: float
    ending_unrealized_pnl: float
    ending_equity: float


def normalize_sleeve_order_input(side: str, symbol: str) -> tuple[str, str]:
    normalized_side = side.lower().strip()
    normalized_symbol = symbol.upper().strip()
    if normalized_side not in VALID_FILL_SIDES:
        raise ValueError("side must be one of: buy, sell")
    if not normalized_symbol:
        raise ValueError("symbol cannot be empty")
    return normalized_side, normalized_symbol


def compute_sleeve_equity(cash: float, market_value_by_symbol: dict[str, float]) -> float:
    return float(cash) + sum(float(value) for value in market_value_by_symbol.values())


def _validate_fill_values(*, side: str, qty: float, fill_price: float, commission: float) -> None:
    if qty <= 0:
        raise ValueError("Fill quantity must be > 0.")
    if side == "buy" and fill_price <= 0:
        raise ValueError("Fill price must be > 0 for buys.")
    if fill_price < 0:
        raise ValueError("Fill price must be >= 0.")
    if commission < 0:
        raise ValueError("Commission must be >= 0.")


def _compute_slippage_amount(
    *,
    side: str,
    qty: float,
    fill_price: float,
    requested_price: float | None,
) -> float:
    if requested_price is None:
        return 0.0
    expected_notional = float(requested_price) * qty
    actual_notional = fill_price * qty
    if side == "buy":
        return actual_notional - expected_notional
    return expected_notional - actual_notional


def apply_sleeve_fill_transition(
    *,
    side: str,
    symbol: str,
    qty: float,
    fill_price: float,
    commission: float,
    requested_price: float | None,
    position_qty: float,
    position_avg_cost: float,
    cash: float,
    realized_pnl: float,
) -> SleeveFillTransition:
    normalized_side, normalized_symbol = normalize_sleeve_order_input(side, symbol)
    fill_qty = float(qty)
    fill_px = float(fill_price)
    fill_commission = float(commission)
    starting_qty = float(position_qty)
    starting_avg_cost = float(position_avg_cost)
    starting_cash = float(cash)
    starting_realized_pnl = float(realized_pnl)

    _validate_fill_values(
        side=normalized_side,
        qty=fill_qty,
        fill_price=fill_px,
        commission=fill_commission,
    )
    if normalized_side == "sell" and fill_qty > starting_qty:
        raise ValueError(f"Invalid sell for {normalized_symbol}: trying to sell {fill_qty}, holding {starting_qty}.")

    if normalized_side == "buy":
        trade_value = fill_qty * fill_px + fill_commission
        ending_qty = starting_qty + fill_qty
        old_value = starting_qty * starting_avg_cost
        ending_avg_cost = (old_value + trade_value) / ending_qty
        cash_delta = -trade_value
        realized_pnl_delta = 0.0
    else:
        proceeds = fill_qty * fill_px - fill_commission
        ending_qty = starting_qty - fill_qty
        ending_avg_cost = 0.0 if ending_qty == 0 else starting_avg_cost
        cash_delta = proceeds
        realized_pnl_delta = (fill_px - starting_avg_cost) * fill_qty - fill_commission

    ending_cash = starting_cash + cash_delta
    ending_realized_pnl = starting_realized_pnl + realized_pnl_delta
    ending_market_value = ending_qty * fill_px
    ending_unrealized_pnl = ending_market_value - (ending_qty * ending_avg_cost)
    ending_equity = ending_cash + ending_market_value

    return SleeveFillTransition(
        symbol=normalized_symbol,
        side=normalized_side,
        qty=fill_qty,
        fill_price=fill_px,
        commission=fill_commission,
        requested_price=float(requested_price) if requested_price is not None else None,
        cash_delta=cash_delta,
        realized_pnl_delta=realized_pnl_delta,
        slippage_amount=_compute_slippage_amount(
            side=normalized_side,
            qty=fill_qty,
            fill_price=fill_px,
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
