from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class SleeveFillRecord:
    """Persisted sleeve_fills row materialized from the database."""

    id: int
    sleeve_order_id: int
    sleeve_id: int
    broker_fill_id: str | None
    exec_id: str | None
    symbol: str
    filled_qty: float
    fill_price: float
    commission: float
    fill_time: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SleeveFillRecord:
        return cls(
            id=row_expect_int(values, "id"),
            sleeve_order_id=row_expect_int(values, "sleeve_order_id"),
            sleeve_id=row_expect_int(values, "sleeve_id"),
            broker_fill_id=row_str(values, "broker_fill_id"),
            exec_id=row_str(values, "exec_id"),
            symbol=row_expect_str(values, "symbol"),
            filled_qty=row_expect_float(values, "filled_qty"),
            fill_price=row_expect_float(values, "fill_price"),
            commission=row_expect_float(values, "commission"),
            fill_time=row_expect_str(values, "fill_time"),
        )
