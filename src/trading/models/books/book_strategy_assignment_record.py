from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class BookStrategyAssignmentRecord:
    """Persisted book_strategy_history row materialized from the database.

    The open row (``effective_to is None``) is the book's incumbent assignment;
    closed rows are prior assignments. There is no dedicated incumbent flag —
    "incumbent" is defined by ``effective_to``.
    """

    id: int
    book_id: int
    strategy_id: int
    effective_from: str
    effective_to: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookStrategyAssignmentRecord:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            strategy_id=row_expect_int(values, "strategy_id"),
            effective_from=row_expect_str(values, "effective_from"),
            effective_to=row_str(values, "effective_to"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
