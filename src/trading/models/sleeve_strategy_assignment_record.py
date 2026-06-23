from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_int, row_str


@dataclass(frozen=True, slots=True)
class SleeveStrategyAssignmentRecord:
    """Persisted sleeve_strategy_assignments row materialized from the database."""

    id: int
    sleeve_id: int
    strategy_name: str
    param_set_id: int | None
    effective_from: str
    effective_to: str | None
    is_incumbent: int
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SleeveStrategyAssignmentRecord:
        return cls(
            id=row_expect_int(values, "id"),
            sleeve_id=row_expect_int(values, "sleeve_id"),
            strategy_name=row_expect_str(values, "strategy_name"),
            param_set_id=row_int(values, "param_set_id"),
            effective_from=row_expect_str(values, "effective_from"),
            effective_to=row_str(values, "effective_to"),
            is_incumbent=row_expect_int(values, "is_incumbent"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
