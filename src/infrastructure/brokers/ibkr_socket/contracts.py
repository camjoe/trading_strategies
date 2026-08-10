"""Backend-neutral records for the IBKR socket client boundary."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IbkrOrderRequest:
    """Order fields required by either socket backend."""

    symbol: str
    action: str
    total_quantity: float
    order_type: str
    limit_price: float
    time_in_force: str
    # IB's orderRef, carrying the caller's client order id. IB echoes it on
    # openOrder, which is what lets a sent-but-unconfirmed order be recognized.
    order_ref: str = ""


@dataclass(frozen=True)
class IbkrFill:
    """Normalized IBKR execution and commission details."""

    shares: float
    price: float
    time: str
    commission: float = 0.0
    exec_id: str | None = None


@dataclass(frozen=True)
class IbkrTrade:
    """Normalized order state returned by a socket backend."""

    order_id: int
    symbol: str
    action: str
    total_quantity: float
    limit_price: float
    status: str
    filled: float
    avg_fill_price: float | None
    fills: tuple[IbkrFill, ...] = field(default_factory=tuple)
    status_reason: str | None = None
    # Empty for an order placed outside this system, which carries no orderRef.
    order_ref: str = ""


@dataclass(frozen=True)
class IbkrPosition:
    """Normalized broker position."""

    symbol: str
    quantity: float


@dataclass(frozen=True)
class IbkrAccountValue:
    """Normalized account-summary value."""

    tag: str
    value: str
    currency: str


@dataclass(frozen=True)
class IbkrQuote:
    """Normalized real-time quote snapshot."""

    symbol: str
    bid: float
    ask: float
    last: float


@dataclass(frozen=True)
class IbkrApiError:
    """Error delivered by the native IBKR socket callback."""

    request_id: int
    code: int
    message: str
    advanced_rejection: str | None = None
