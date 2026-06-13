from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str


@dataclass(frozen=True, slots=True)
class EquitySnapshotRecord:
    """Persisted equity_snapshots row materialized from the database."""

    id: int
    account_id: int
    snapshot_time: str
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> EquitySnapshotRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            snapshot_time=row_expect_str(values, "snapshot_time"),
            cash=row_expect_float(values, "cash"),
            market_value=row_expect_float(values, "market_value"),
            equity=row_expect_float(values, "equity"),
            realized_pnl=row_expect_float(values, "realized_pnl"),
            unrealized_pnl=row_expect_float(values, "unrealized_pnl"),
        )
