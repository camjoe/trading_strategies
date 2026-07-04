from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class UnitStrategyAssignmentRecord:
    """Persisted unit_strategy_assignments row materialized from the database."""

    id: int
    unit_id: int
    strategy_id: int
    effective_from: str
    effective_to: str | None
    is_incumbent: int
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> UnitStrategyAssignmentRecord:
        return cls(
            id=row_expect_int(values, "id"),
            unit_id=row_expect_int(values, "unit_id"),
            strategy_id=row_expect_int(values, "strategy_id"),
            effective_from=row_expect_str(values, "effective_from"),
            effective_to=row_str(values, "effective_to"),
            is_incumbent=row_expect_int(values, "is_incumbent"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
