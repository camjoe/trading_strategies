from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_int


@dataclass(frozen=True, slots=True)
class EquitySnapshotRecord:
    """Equity snapshot row (book-keyed storage; account view is the roll-up).

    ``book_id`` and ``id`` are coupled: both are real on a single-book read, and
    both are ``None`` on a multi-book account roll-up row aggregated across books
    (a synthetic aggregate is not an addressable stored row, so it carries no
    id). ``account_id`` is carried by every repository query for consumer
    context.
    """

    id: int | None
    account_id: int
    book_id: int | None
    snapshot_time: str
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> EquitySnapshotRecord:
        return cls(
            id=row_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            book_id=row_int(values, "book_id"),
            snapshot_time=row_expect_str(values, "snapshot_time"),
            cash=row_expect_float(values, "cash"),
            market_value=row_expect_float(values, "market_value"),
            equity=row_expect_float(values, "equity"),
            realized_pnl=row_expect_float(values, "realized_pnl"),
            unrealized_pnl=row_expect_float(values, "unrealized_pnl"),
        )
