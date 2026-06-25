from __future__ import annotations

import sqlite3

from trading.models.sleeves.sleeve_ledger_record import SleeveLedgerRecord


class SleeveLedgerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> SleeveLedgerRecord:
        return SleeveLedgerRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        sleeve_id: int,
        entry_type: str,
        amount: float,
        reference_type: str | None,
        reference_id: str | None,
        entry_time: str,
        created_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO sleeve_ledger (
                sleeve_id,
                entry_type,
                amount,
                reference_type,
                reference_id,
                entry_time,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(sleeve_id),
                entry_type,
                float(amount),
                reference_type,
                reference_id,
                entry_time,
                created_at,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected sleeve_ledger id after insert.")
        return int(cursor.lastrowid)

    def fetch_for_sleeve(self, *, sleeve_id: int, limit: int) -> list[SleeveLedgerRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sleeve_ledger
            WHERE sleeve_id = ?
            ORDER BY entry_time DESC, id DESC
            LIMIT ?
            """,
            (int(sleeve_id), int(limit)),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_sum_by_type(self, *, sleeve_id: int, entry_type: str) -> float:
        row = self._conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total_amount
            FROM sleeve_ledger
            WHERE sleeve_id = ? AND entry_type = ?
            """,
            (int(sleeve_id), entry_type),
        ).fetchone()
        if row is None:
            return 0.0
        return float(row["total_amount"])
