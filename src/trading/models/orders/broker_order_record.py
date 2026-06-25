from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float
from trading.models.orders.broker_order import OrderStatus, OrderType, TimeInForce


@dataclass(frozen=True, slots=True)
class BrokerOrderRecord:
    """Persisted broker_orders row materialized from the database."""

    id: int
    account_id: int
    broker_order_id: str
    ticker: str
    side: str
    qty: float
    order_type: OrderType
    time_in_force: TimeInForce
    requested_price: float
    status: OrderStatus
    filled_qty: float
    avg_fill_price: float | None
    commission: float
    submitted_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BrokerOrderRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            broker_order_id=row_expect_str(values, "broker_order_id"),
            ticker=row_expect_str(values, "ticker"),
            side=row_expect_str(values, "side"),
            qty=row_expect_float(values, "qty"),
            order_type=OrderType(row_expect_str(values, "order_type")),
            time_in_force=TimeInForce(row_expect_str(values, "time_in_force")),
            requested_price=row_expect_float(values, "requested_price"),
            status=OrderStatus(row_expect_str(values, "status")),
            filled_qty=row_expect_float(values, "filled_qty"),
            avg_fill_price=row_float(values, "avg_fill_price"),
            commission=row_expect_float(values, "commission"),
            submitted_at=row_expect_str(values, "submitted_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
