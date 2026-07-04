from __future__ import annotations

import sqlite3

from trading.models.units.ledger_entry_record import LedgerEntryRecord


class LedgerRepository:
    """SQL access for the clean-schema unit-keyed ledger."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> LedgerEntryRecord:
        return LedgerEntryRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        unit_id: int,
        entry_type: str,
        amount: float,
        reference_type: str | None = None,
        reference_id: str | None = None,
        entry_time: str,
        created_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO ledger (
                unit_id, entry_type, amount, reference_type, reference_id,
                entry_time, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(unit_id),
                entry_type,
                float(amount),
                reference_type,
                reference_id,
                entry_time,
                created_at,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def fetch_for_unit(self, *, unit_id: int) -> list[LedgerEntryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM ledger WHERE unit_id = ? ORDER BY entry_time ASC, id ASC",
            (int(unit_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_by_reference(self, *, reference_type: str, reference_id: str) -> list[LedgerEntryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM ledger WHERE reference_type = ? AND reference_id = ? ORDER BY id ASC",
            (reference_type, reference_id),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
