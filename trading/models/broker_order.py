"""Broker order data models.

These types represent the lifecycle of a broker order and its fills.
Kept in ``trading/models/`` so that repositories and services can use them
without depending on the ``trading/brokers/`` package.
"""
from __future__ import annotations

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
