from __future__ import annotations

import sqlite3

from trading.models.units.unit_strategy_assignment_record import UnitStrategyAssignmentRecord


class UnitAssignmentRepository:
    """SQL access for unit_strategy_assignments.

    The one-open-assignment-per-unit invariant is enforced by the partial unique
    index `idx_unit_assignments_open_per_unit`; `assign_strategy` closes the open
    row (if any) and opens the new one in a single transaction.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> UnitStrategyAssignmentRecord:
        return UnitStrategyAssignmentRecord.from_mapping(dict(row))

    def fetch_open(self, *, unit_id: int) -> UnitStrategyAssignmentRecord | None:
        row = self._conn.execute(
            "SELECT * FROM unit_strategy_assignments WHERE unit_id = ? AND effective_to IS NULL",
            (int(unit_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_history(self, *, unit_id: int) -> list[UnitStrategyAssignmentRecord]:
        rows = self._conn.execute(
            "SELECT * FROM unit_strategy_assignments WHERE unit_id = ? ORDER BY effective_from ASC, id ASC",
            (int(unit_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def assign_strategy(
        self,
        *,
        unit_id: int,
        strategy_id: int,
        effective_from: str,
        created_at: str,
        updated_at: str,
    ) -> int:
        """Close the unit's open assignment (if any) and open a new incumbent."""
        try:
            self._conn.execute(
                """
                UPDATE unit_strategy_assignments
                SET effective_to = ?, is_incumbent = 0, updated_at = ?
                WHERE unit_id = ? AND effective_to IS NULL
                """,
                (effective_from, updated_at, int(unit_id)),
            )
            cursor = self._conn.execute(
                """
                INSERT INTO unit_strategy_assignments (
                    unit_id, strategy_id, effective_from, effective_to, is_incumbent,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, 1, ?, ?)
                """,
                (int(unit_id), int(strategy_id), effective_from, created_at, updated_at),
            )
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return int(cursor.lastrowid or 0)
