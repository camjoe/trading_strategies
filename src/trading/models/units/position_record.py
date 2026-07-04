from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str


@dataclass(frozen=True, slots=True)
class PositionRecord:
    """Persisted positions row (unit-keyed) materialized from the database."""

    unit_id: int
    symbol: str
    qty: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> PositionRecord:
        return cls(
            unit_id=row_expect_int(values, "unit_id"),
            symbol=row_expect_str(values, "symbol"),
            qty=row_expect_float(values, "qty"),
            avg_cost=row_expect_float(values, "avg_cost"),
            market_value=row_expect_float(values, "market_value"),
            unrealized_pnl=row_expect_float(values, "unrealized_pnl"),
            updated_at=row_expect_str(values, "updated_at"),
        )
