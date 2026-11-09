"""Whether the cash the books hold is cash the broker can actually spend."""

from __future__ import annotations

from decimal import Decimal

# Cash the books may hold above the broker's figure before it counts as a shortfall: absorbs
# cent rounding between the ledger and the broker's cash balance.
BROKER_CASH_TOLERANCE = Decimal("1.00")

# The Web API reaches one IBKR account, the one named in its settings, whichever Web broker type
# an account uses.
_WEB_BROKER_TYPES = frozenset({"interactive_brokers_web", "interactive_brokers_web_paper"})
_WEB_POOL = "ibkr_web"

# The socket transport reaches whichever TWS or IB Gateway answers at an account's host and port.
_SOCKET_BROKER_TYPES = frozenset({"interactive_brokers_socket", "interactive_brokers_socket_paper"})


def broker_cash_pool(broker_type: str | None, broker_host: str | None, broker_port: int | None) -> str | None:
    """Name the broker cash balance an account's books draw on, or None when the broker keeps no cash.

    Accounts with the same pool name spend from one real balance. A simulator account has no pool.
    The broker type is read as the broker factory reads it, trimmed and lower-cased. An unset host and port name
    their own pool, which the socket factory resolves to its defaults.
    """
    normalized = (broker_type or "").strip().lower()
    if normalized in _WEB_BROKER_TYPES:
        return _WEB_POOL
    if normalized in _SOCKET_BROKER_TYPES:
        return f"ibkr_socket:{broker_host or ''}:{broker_port or 0}"
    return None


def broker_cash_shortfall(book_cash: Decimal, broker_cash: float) -> Decimal:
    """How far the books' cash exceeds the broker's, beyond the tolerance; zero when it does not."""
    excess = book_cash - Decimal(str(broker_cash)) - BROKER_CASH_TOLERANCE
    return max(excess, Decimal(0))
