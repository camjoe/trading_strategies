"""Broker interface — abstract contract for order submission and account queries.

All broker adapters must implement :class:`BrokerConnection`.  The domain and
service layers depend only on this module; concrete adapters are injected at
the runtime / interface layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(Enum):
    # Order valid for the current trading session only.
    DAY = "day"
    # Order remains open until explicitly cancelled.
    GTC = "gtc"
    # Fill immediately or cancel any unfilled portion.
    IOC = "ioc"


@dataclass
class OrderFill:
    """A single execution report for part of a broker order."""

    filled_qty: float
    fill_price: float
    fill_time: str  # ISO-8601 UTC string
    commission: float
    # IB execution ID — unique per execution report; None for paper fills.
    exec_id: str | None = None


@dataclass
class BrokerOrder:
    """Represents an order through its full lifecycle: creation → fills → final status.

    Fields set by the caller before :meth:`BrokerConnection.place_order`:
        account_id, ticker, side, qty, price, order_type, time_in_force

    Fields set (or updated) by the broker after placement:
        broker_order_id, status, filled_qty, avg_fill_price, commission,
        submitted_at, updated_at, fills
    """

    account_id: int
    ticker: str
    side: str  # "buy" | "sell"
    qty: float
    # Requested price — used as limit price for LIMIT orders; informational for MARKET orders.
    price: float
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY

    # Set after broker placement
    broker_order_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    # Total commission charged (0.0 for paper trading)
    commission: float = 0.0
    submitted_at: str | None = None
    updated_at: str | None = None
    fills: list[OrderFill] = field(default_factory=list)


class BrokerConnection(ABC):
    """Abstract interface over a broker connection.

    Implement this class to add a new broker.  Register the adapter in
    :func:`trading.brokers.factory.get_broker_for_account`.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the broker endpoint."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection gracefully."""

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        """Submit *order* and return it populated with broker-assigned fields.

        For synchronous/paper brokers the returned order will have
        ``status == OrderStatus.FILLED``.  For async live brokers the status
        will be ``SUBMITTED`` initially and updated via separate fill events.
        """

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None:
        """Request cancellation of an open order."""

    @abstractmethod
    def get_positions(self) -> dict[str, float]:
        """Return current live positions as ``{ticker: qty}``."""

    @abstractmethod
    def get_account_info(self) -> dict[str, float]:
        """Return account summary: ``cash``, ``buying_power``, ``market_value``, etc."""

    @abstractmethod
    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        """Return real-time quotes for *tickers* as ``{ticker: {bid, ask, last}}``."""
