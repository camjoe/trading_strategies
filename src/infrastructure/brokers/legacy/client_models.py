"""Backend-neutral records for the legacy IBKR socket client boundary."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LegacyOrderRequest:
    """Order fields required by either legacy socket backend."""

    symbol: str
    action: str
    total_quantity: float
    order_type: str
    limit_price: float
    time_in_force: str


@dataclass(frozen=True)
class LegacyFill:
    """Normalized IBKR execution and commission details."""

    shares: float
    price: float
    time: str
    commission: float = 0.0
    exec_id: str | None = None


@dataclass(frozen=True)
class LegacyTrade:
    """Normalized order state returned by a legacy socket backend."""

    order_id: int
    symbol: str
    action: str
    total_quantity: float
    limit_price: float
    status: str
    filled: float
    avg_fill_price: float | None
    fills: tuple[LegacyFill, ...] = field(default_factory=tuple)
    status_reason: str | None = None


@dataclass(frozen=True)
class LegacyPosition:
    """Normalized broker position."""

    symbol: str
    quantity: float


@dataclass(frozen=True)
class LegacyAccountValue:
    """Normalized account-summary value."""

    tag: str
    value: str
    currency: str


@dataclass(frozen=True)
class LegacyQuote:
    """Normalized real-time quote snapshot."""

    symbol: str
    bid: float
    ask: float
    last: float
