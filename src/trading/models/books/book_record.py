from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_str


@dataclass(frozen=True, slots=True)
class BookRecord:
    """Persisted books row materialized from the database."""

    id: int
    account_id: int
    name: str
    status: str
    is_default: int
    start_equity: float
    current_cash: float
    current_equity: float
    trade_universes: str | None
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            name=row_expect_str(values, "name"),
            status=row_expect_str(values, "status"),
            is_default=row_expect_int(values, "is_default"),
            start_equity=row_expect_float(values, "start_equity"),
            current_cash=row_expect_float(values, "current_cash"),
            current_equity=row_expect_float(values, "current_equity"),
            trade_universes=row_str(values, "trade_universes"),
            goal_min_return_pct=row_float(values, "goal_min_return_pct"),
            goal_max_return_pct=row_float(values, "goal_max_return_pct"),
            goal_period=row_str(values, "goal_period"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
