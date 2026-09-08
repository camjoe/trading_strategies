"""Shared order-input validation for account trades and book fills — pure, no I/O."""

from __future__ import annotations

# Supported order directions for both account trades and book fills.
VALID_SIDES = {"buy", "sell"}


def normalize_order_input(side: str, symbol: str, *, require_symbol: bool = False) -> tuple[str, str]:
    """Lower-case the side and upper-case the symbol, validating the side.

    Pass ``require_symbol=True`` to also reject an empty symbol (book fills need a
    concrete instrument; the manual-trade path tolerates the settlement ticker).
    """
    normalized_side = side.lower().strip()
    normalized_symbol = symbol.upper().strip()
    if normalized_side not in VALID_SIDES:
        raise ValueError("side must be one of: buy, sell")
    if require_symbol and not normalized_symbol:
        raise ValueError("symbol cannot be empty")
    return normalized_side, normalized_symbol


def validate_order_values(
    *,
    side: str,
    qty: float,
    price: float,
    commission: float | None = None,
    noun: str,
) -> None:
    """Reject non-positive quantity, a non-positive buy price, and negative values.

    ``noun`` names the value in the error text ("Trade" or "Fill"). A ``$0`` sell is
    valid (e.g. an expired option); a ``$0`` buy is not. ``commission`` is checked
    only when supplied.
    """
    if qty <= 0:
        raise ValueError(f"{noun} quantity must be > 0.")
    if side == "buy" and price <= 0:
        raise ValueError(f"{noun} price must be > 0.")
    if price < 0:
        raise ValueError(f"{noun} price must be >= 0.")
    if commission is not None and commission < 0:
        raise ValueError("Commission must be >= 0.")


def ensure_sufficient_cash_for_buy(
    side: str,
    qty: float,
    price: float,
    fee: float,
    available_cash: float,
) -> None:
    """Raise if a buy's notional plus fee exceeds ``available_cash``. Sells are exempt."""
    if side != "buy":
        return
    required_cash = qty * price + fee
    if required_cash > available_cash:
        raise ValueError(f"Insufficient cash: need {required_cash:.2f}, available {available_cash:.2f}.")
