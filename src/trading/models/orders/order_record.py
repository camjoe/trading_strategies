from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class OrderRecord:
    """Persisted orders row (clean schema, book-keyed) materialized from the database."""

    id: int
    book_id: int
    account_id: int
    strategy_id: int | None
    rotation_decision_id: int | None
    broker_order_id: str | None
    symbol: str
    side: str
    qty: float
    order_type: str
    time_in_force: str
    requested_price: float | None
    status: str
    filled_qty: float
    avg_fill_price: float | None
    commission: float
    submitted_at: str
    updated_at: str
    status_reason: str | None = None

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
        )
