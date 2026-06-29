from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class SleeveLedgerRecord:
    """Persisted sleeve_ledger row materialized from the database."""

    id: int
    sleeve_id: int
    entry_type: str
    amount: float
    reference_type: str | None
    reference_id: str | None
    entry_time: str
    created_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SleeveLedgerRecord:
        return cls(
            id=row_expect_int(values, "id"),
            sleeve_id=row_expect_int(values, "sleeve_id"),
            entry_type=row_expect_str(values, "entry_type"),
            amount=row_expect_float(values, "amount"),
            reference_type=row_str(values, "reference_type"),
            reference_id=row_str(values, "reference_id"),
            entry_time=row_expect_str(values, "entry_time"),
            created_at=row_expect_str(values, "created_at"),
        )
