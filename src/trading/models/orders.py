"""Order data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str


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
    # Broker-supplied reason for a terminal non-fill status (rejected / cancelled);
    # None until an adapter surfaces it. Persisted to orders.status_reason.
    status_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FillEventRecord:
    """One execution joined to its order, shaped for the account-state replay.

    Field names mirror the retired ``trades`` row so the pure replay math in
    ``trading.domain.accounting`` reads them unchanged.
    """

    book_id: int
    ticker: str
    side: str
    qty: float
    price: float
    fee: float
    trade_time: str
    order_id: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> FillEventRecord:
        return cls(
            book_id=row_expect_int(values, "book_id"),
            ticker=row_expect_str(values, "ticker"),
            side=row_expect_str(values, "side"),
            qty=row_expect_float(values, "qty"),
            price=row_expect_float(values, "price"),
            fee=row_expect_float(values, "fee"),
            trade_time=row_expect_str(values, "trade_time"),
            order_id=row_expect_int(values, "order_id"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderInsert:
    """The orders columns a caller supplies when creating a row.

    Field names are the column names: `OrderRepository` builds both the INSERT
    column list and its values from this class, so a field with no column is a
    failed insert.
    """

    book_id: int
    account_id: int
    strategy_id: int | None = None
    rotation_decision_id: int | None = None
    broker_order_id: str | None = None
    symbol: str
    side: str
    qty: float
    order_type: str = OrderType.MARKET.value
    time_in_force: str = TimeInForce.DAY.value
    requested_price: float | None = None
    status: str
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    commission: float = 0.0
    submitted_at: str
    updated_at: str
    status_reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderRecord(OrderInsert):
    """Persisted orders row (clean schema, book-keyed) materialized from the database.

    The insert payload plus the two columns the database owns: `id` on write, and
    `realized_pnl_delta` accrued afterwards by `OrderRepository.add_realized_pnl_delta`.
    """

    id: int
    # Realized P&L for a closing order (sell), net of commission. NULL for opening
    # orders (buys realize nothing) — so NOT NULL identifies a closing trade.
    realized_pnl_delta: float | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> OrderRecord:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            account_id=row_expect_int(values, "account_id"),
            strategy_id=row_int(values, "strategy_id"),
            rotation_decision_id=row_int(values, "rotation_decision_id"),
            broker_order_id=row_str(values, "broker_order_id"),
            symbol=row_expect_str(values, "symbol"),
            side=row_expect_str(values, "side"),
            qty=row_expect_float(values, "qty"),
            order_type=row_expect_str(values, "order_type"),
            time_in_force=row_expect_str(values, "time_in_force"),
            requested_price=row_float(values, "requested_price"),
            status=row_expect_str(values, "status"),
            filled_qty=row_expect_float(values, "filled_qty"),
            avg_fill_price=row_float(values, "avg_fill_price"),
            commission=row_expect_float(values, "commission"),
            submitted_at=row_expect_str(values, "submitted_at"),
            updated_at=row_expect_str(values, "updated_at"),
            status_reason=row_str(values, "status_reason"),
            realized_pnl_delta=row_float(values, "realized_pnl_delta"),
        )
