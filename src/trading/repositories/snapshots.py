from __future__ import annotations

import sqlite3

from common.time import next_date_str
from trading.models.portfolio import EquitySnapshotRecord
from trading.persistence.unit_of_work import commit_unit_of_work

# Account-view roll-up over the account's books: one row per snapshot_time with
# summed balances. Degenerates to the raw row while an account has only its
# default book. Multi-book aggregate rows carry NULL book_id AND NULL id: the id
# is coupled to book_id so a synthetic aggregate can never be mistaken for an
# addressable stored row (both are real, or both are NULL).
_ACCOUNT_VIEW_SELECT = """
SELECT
    CASE WHEN COUNT(DISTINCT s.book_id) = 1 THEN MIN(s.id) ELSE NULL END AS id,
    b.account_id AS account_id,
    CASE WHEN COUNT(DISTINCT s.book_id) = 1 THEN MIN(s.book_id) ELSE NULL END AS book_id,
    s.snapshot_time AS snapshot_time,
    SUM(s.cash) AS cash,
    SUM(s.market_value) AS market_value,
    SUM(s.equity) AS equity,
    SUM(s.realized_pnl) AS realized_pnl,
    SUM(s.unrealized_pnl) AS unrealized_pnl
FROM equity_snapshots s
JOIN books b ON b.id = s.book_id
WHERE b.account_id = ?
GROUP BY s.snapshot_time
"""

# Time-bounded variants for window slicing (equity at/after a window start, or
# at/before a window end). The extra predicate goes inside the WHERE, before the
# GROUP BY, so it filters the raw rows that are rolled up per snapshot_time.
_ACCOUNT_VIEW_SELECT_WITH_LOWER_BOUND = _ACCOUNT_VIEW_SELECT.replace(
    "WHERE b.account_id = ?",
    "WHERE b.account_id = ?\n  AND s.snapshot_time >= ?",
)
_ACCOUNT_VIEW_SELECT_WITH_UPPER_BOUND = _ACCOUNT_VIEW_SELECT.replace(
    "WHERE b.account_id = ?",
    "WHERE b.account_id = ?\n  AND s.snapshot_time <= ?",
)

# The raw stored row for one book — no roll-up, so `id` and `book_id` are real.
_BOOK_ROW_SELECT = """
SELECT s.id AS id, b.account_id AS account_id, s.book_id AS book_id, s.snapshot_time AS snapshot_time,
       s.cash AS cash, s.market_value AS market_value, s.equity AS equity,
       s.realized_pnl AS realized_pnl, s.unrealized_pnl AS unrealized_pnl
FROM equity_snapshots s
JOIN books b ON b.id = s.book_id
"""

_SNAPSHOT_TIME_COUNT = """
SELECT COUNT(DISTINCT s.snapshot_time) AS snapshot_count
FROM equity_snapshots s
JOIN books b ON b.id = s.book_id
"""

# The account view aliases its id column, so it orders on the bare name.
_ACCOUNT_NEWEST_FIRST = "s.snapshot_time DESC, id DESC"
_ACCOUNT_OLDEST_FIRST = "s.snapshot_time ASC, id ASC"
_BOOK_NEWEST_FIRST = "s.snapshot_time DESC, s.id DESC"


class EquitySnapshotRepository:
    """Book-keyed snapshot storage with account-level roll-up reads.

    Grain: **book-additive**. Balances sum across books, so every account-view
    read (`fetch_latest`, `fetch_history`, ...) returns one *rolled-up* row per
    `snapshot_time` — a `SUM` over the account's books. Multi-book aggregate
    rows carry NULL `book_id` and NULL `id` (they are not addressable stored
    rows). Contrast `DailyMetricsRepository` (book-native, non-additive) and
    `RiskSnapshotRepository` (account-emergent); see
    docs/reference/performance-and-risk-tables.md.

    Writes are book-keyed only. Choosing which book an account-scoped caller
    means is service work — see `services/books/default_book.py`.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_for_book(
        self,
        *,
        book_id: int,
        snapshot_time: str,
        cash: float,
        market_value: float,
        equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO equity_snapshots (
                book_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (book_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
        )
        commit_unit_of_work(self._conn)

    def _fetch_one(self, select: str, order: str, params: tuple[object, ...]) -> EquitySnapshotRecord | None:
        row = self._conn.execute(f"{select} ORDER BY {order} LIMIT 1", params).fetchone()
        return EquitySnapshotRecord.from_mapping(dict(row)) if row is not None else None

    def _count_snapshot_times(self, filter_sql: str, params: tuple[object, ...]) -> int:
        row = self._conn.execute(_SNAPSHOT_TIME_COUNT + filter_sql, params).fetchone()
        return int(row["snapshot_count"]) if row is not None else 0

    def fetch_history(self, *, account_id: int, limit: int) -> list[EquitySnapshotRecord]:
        rows = self._conn.execute(
            f"{_ACCOUNT_VIEW_SELECT} ORDER BY {_ACCOUNT_NEWEST_FIRST} LIMIT ?",
            (account_id, limit),
        ).fetchall()
        return [EquitySnapshotRecord.from_mapping(dict(row)) for row in rows]

    def fetch_history_for_book(self, *, book_id: int, limit: int) -> list[EquitySnapshotRecord]:
        rows = self._conn.execute(
            f"{_BOOK_ROW_SELECT} WHERE s.book_id = ? ORDER BY {_BOOK_NEWEST_FIRST} LIMIT ?",
            (book_id, limit),
        ).fetchall()
        return [EquitySnapshotRecord.from_mapping(dict(row)) for row in rows]

    def fetch_count_between(self, *, account_id: int, start_iso: str, end_iso: str) -> int:
        return self._count_snapshot_times(
            "WHERE b.account_id = ? AND s.snapshot_time >= ? AND s.snapshot_time <= ?",
            (account_id, start_iso, end_iso),
        )

    def fetch_count(self, *, account_id: int) -> int:
        return self._count_snapshot_times("WHERE b.account_id = ?", (account_id,))

    def fetch_latest(self, *, account_id: int) -> EquitySnapshotRecord | None:
        return self._fetch_one(_ACCOUNT_VIEW_SELECT, _ACCOUNT_NEWEST_FIRST, (account_id,))

    def fetch_max_equity(self, *, account_id: int) -> float | None:
        """The account's highest rolled-up equity ever recorded, or None with no snapshots.

        Used as the running-peak input for point-in-time drawdown (see
        ``risk_snapshots.drawdown_pct``): the caller compares current equity
        against this historical peak.
        """
        row = self._conn.execute(
            f"SELECT MAX(equity) AS max_equity FROM ({_ACCOUNT_VIEW_SELECT}) AS account_equity",
            (account_id,),
        ).fetchone()
        value = row["max_equity"] if row is not None else None
        return float(value) if value is not None else None

    def fetch_earliest(self, *, account_id: int) -> EquitySnapshotRecord | None:
        return self._fetch_one(_ACCOUNT_VIEW_SELECT, _ACCOUNT_OLDEST_FIRST, (account_id,))

    def fetch_first_at_or_after(self, *, account_id: int, iso: str) -> EquitySnapshotRecord | None:
        return self._fetch_one(_ACCOUNT_VIEW_SELECT_WITH_LOWER_BOUND, _ACCOUNT_OLDEST_FIRST, (account_id, iso))

    def fetch_last_for_book_on_or_before_date(self, *, book_id: int, date_str: str) -> EquitySnapshotRecord | None:
        """Latest raw snapshot for one book whose calendar date is <= ``date_str``.

        Per-book (no account roll-up).
        """
        return self._fetch_last_book_snapshot_before(book_id=book_id, before=next_date_str(date_str))

    def fetch_last_for_book_before_date(self, *, book_id: int, date_str: str) -> EquitySnapshotRecord | None:
        """Latest raw snapshot for one book whose calendar date is strictly < ``date_str``."""
        return self._fetch_last_book_snapshot_before(book_id=book_id, before=date_str)

    def _fetch_last_book_snapshot_before(self, *, book_id: int, before: str) -> EquitySnapshotRecord | None:
        """Latest raw snapshot for one book strictly below the ``before`` bound.

        ``before`` is a bare ``YYYY-MM-DD``, which sorts below every stored
        timestamp on that day, so the bound excludes the whole day.
        """
        return self._fetch_one(
            f"{_BOOK_ROW_SELECT} WHERE s.book_id = ? AND s.snapshot_time < ?",
            _BOOK_NEWEST_FIRST,
            (book_id, before),
        )

    def fetch_last_at_or_before(self, *, account_id: int, iso: str) -> EquitySnapshotRecord | None:
        return self._fetch_one(_ACCOUNT_VIEW_SELECT_WITH_UPPER_BOUND, _ACCOUNT_NEWEST_FIRST, (account_id, iso))
