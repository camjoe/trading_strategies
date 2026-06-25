from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class SleeveRecord:
    """Persisted strategy_sleeves row materialized from the database."""

    id: int
    account_id: int
    name: str
    status: str
    base_ccy: str
    start_equity: float
    current_cash: float
    current_equity: float
    created_at: str
    updated_at: str
    trade_universes: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SleeveRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            name=row_expect_str(values, "name"),
            status=row_expect_str(values, "status"),
            base_ccy=row_expect_str(values, "base_ccy"),
            start_equity=row_expect_float(values, "start_equity"),
            current_cash=row_expect_float(values, "current_cash"),
            current_equity=row_expect_float(values, "current_equity"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
            trade_universes=row_str(values, "trade_universes"),
        )
