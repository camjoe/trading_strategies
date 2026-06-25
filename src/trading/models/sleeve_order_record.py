from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_int, row_str


@dataclass(frozen=True, slots=True)
class SleeveOrderRecord:
    """Persisted sleeve_orders row materialized from the database."""

    id: int
    account_id: int
    sleeve_id: int
    strategy_name: str
    param_set_id: int | None
    rotation_decision_id: int | None
    broker_order_id: str | None
    symbol: str
    side: str
    qty: float
    order_type: str
    time_in_force: str
    requested_price: float
    status: str
    config_version: str | None
    submitted_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SleeveOrderRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            sleeve_id=row_expect_int(values, "sleeve_id"),
            strategy_name=row_expect_str(values, "strategy_name"),
            param_set_id=row_int(values, "param_set_id"),
            rotation_decision_id=row_int(values, "rotation_decision_id"),
            broker_order_id=row_str(values, "broker_order_id"),
            symbol=row_expect_str(values, "symbol"),
            side=row_expect_str(values, "side"),
            qty=row_expect_float(values, "qty"),
            order_type=row_expect_str(values, "order_type"),
            time_in_force=row_expect_str(values, "time_in_force"),
            requested_price=row_expect_float(values, "requested_price"),
            status=row_expect_str(values, "status"),
            config_version=row_str(values, "config_version"),
            submitted_at=row_expect_str(values, "submitted_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
