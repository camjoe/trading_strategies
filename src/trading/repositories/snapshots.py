from __future__ import annotations

import sqlite3

from trading.models.portfolio.equity_snapshot_record import EquitySnapshotRecord
from trading.repositories.book_bridge import default_book_id

# Account-view roll-up over the account's books: one row per snapshot_time with
# summed balances. Degenerates to the raw row while an account has only its
# default book. Aggregated rows carry NULL book_id.
_ACCOUNT_VIEW_SELECT = """
SELECT
    MIN(s.id) AS id,
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


class EquitySnapshotRepository:
    """Book-keyed snapshot storage with account-level roll-up reads.

    Until P4's shared execution services own the writers, `insert` keeps the
    legacy account-keyed signature and resolves (bootstrapping if needed) the
    account's default book.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> EquitySnapshotRecord:
        return EquitySnapshotRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        account_id: int,
        snapshot_time: str,
        cash: float,
        market_value: float,
        equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
    ) -> None:
        book_id = default_book_id(self._conn, int(account_id))
        self.insert_for_book(
            book_id=book_id,
            snapshot_time=snapshot_time,
            cash=cash,
            market_value=market_value,
            equity=equity,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
        )

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
            (int(book_id), snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
        )
        self._conn.commit()

    def fetch_recent_equity(self, *, account_id: int, limit: int) -> list[float]:
        rows = self._conn.execute(
            _ACCOUNT_VIEW_SELECT + " ORDER BY s.snapshot_time DESC, id DESC LIMIT ?",
            (int(account_id), int(limit)),
        ).fetchall()
        return [float(row["equity"]) for row in rows]

    def fetch_history(self, *, account_id: int, limit: int) -> list[EquitySnapshotRecord]:
        rows = self._conn.execute(
            _ACCOUNT_VIEW_SELECT + " ORDER BY s.snapshot_time DESC, id DESC LIMIT ?",
            (int(account_id), int(limit)),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_count_between(self, *, account_id: int, start_iso: str, end_iso: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(DISTINCT s.snapshot_time) AS snapshot_count
            FROM equity_snapshots s
            JOIN books b ON b.id = s.book_id
            WHERE b.account_id = ?
              AND s.snapshot_time >= ?
              AND s.snapshot_time <= ?
            """,
            (int(account_id), start_iso, end_iso),
        ).fetchone()
        return int(row["snapshot_count"]) if row is not None else 0

    def fetch_count(self, *, account_id: int) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(DISTINCT s.snapshot_time) AS snapshot_count
            FROM equity_snapshots s
            JOIN books b ON b.id = s.book_id
            WHERE b.account_id = ?
            """,
            (int(account_id),),
        ).fetchone()
        return int(row["snapshot_count"]) if row is not None else 0

    def fetch_latest(self, *, account_id: int) -> EquitySnapshotRecord | None:
        row = self._conn.execute(
            _ACCOUNT_VIEW_SELECT + " ORDER BY s.snapshot_time DESC, id DESC LIMIT 1",
            (int(account_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None
