from __future__ import annotations

import sqlite3

from trading.models.equity_snapshot_record import EquitySnapshotRecord


class EquitySnapshotRepository:

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
        self._conn.execute(
            """
            INSERT INTO equity_snapshots (
                account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
        )
        self._conn.commit()

    def fetch_recent_equity(self, *, account_id: int, limit: int) -> list[float]:
        rows = self._conn.execute(
            """
            SELECT equity
            FROM equity_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_time DESC, id DESC
            LIMIT ?
            """,
            (account_id, int(limit)),
        ).fetchall()
        return [float(row["equity"]) for row in rows]

    def fetch_history(self, *, account_id: int, limit: int) -> list[EquitySnapshotRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM equity_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_time DESC, id DESC
            LIMIT ?
            """,
            (account_id, int(limit)),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_count_between(self, *, account_id: int, start_iso: str, end_iso: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS snapshot_count
            FROM equity_snapshots
            WHERE account_id = ?
              AND snapshot_time >= ?
              AND snapshot_time <= ?
            """,
            (int(account_id), start_iso, end_iso),
        ).fetchone()
        return int(row["snapshot_count"]) if row is not None else 0

    def fetch_count(self, *, account_id: int) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS snapshot_count
            FROM equity_snapshots
            WHERE account_id = ?
            """,
            (int(account_id),),
        ).fetchone()
        return int(row["snapshot_count"]) if row is not None else 0

    def fetch_latest(self, *, account_id: int) -> EquitySnapshotRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM equity_snapshots
            WHERE account_id = ?
            ORDER BY snapshot_time DESC, id DESC
            LIMIT 1
            """,
            (int(account_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None
