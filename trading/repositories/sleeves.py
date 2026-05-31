from __future__ import annotations

import sqlite3

from trading.models.sleeve_record import SleeveRecord
from trading.models.sleeve_strategy_assignment_record import SleeveStrategyAssignmentRecord


class SleeveRepository:

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_sleeve(self, row: sqlite3.Row) -> SleeveRecord:
        return SleeveRecord.from_mapping(dict(row))

    def _row_to_assignment(self, row: sqlite3.Row) -> SleeveStrategyAssignmentRecord:
        return SleeveStrategyAssignmentRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        account_id: int,
        name: str,
        status: str,
        base_ccy: str,
        start_equity: float,
        current_cash: float,
        current_equity: float,
        created_at: str,
        updated_at: str,
        trade_universes: str | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO strategy_sleeves (
                account_id,
                name,
                status,
                base_ccy,
                start_equity,
                current_cash,
                current_equity,
                created_at,
                updated_at,
                trade_universes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                name,
                status,
                base_ccy,
                float(start_equity),
                float(current_cash),
                float(current_equity),
                created_at,
                updated_at,
                trade_universes,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected strategy_sleeves id after insert.")
        return int(cursor.lastrowid)

    def fetch_by_id(self, *, sleeve_id: int) -> SleeveRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategy_sleeves WHERE id = ?",
            (int(sleeve_id),),
        ).fetchone()
        return self._row_to_sleeve(row) if row is not None else None

    def fetch_for_account(self, *, account_id: int) -> list[SleeveRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM strategy_sleeves
            WHERE account_id = ?
            ORDER BY id ASC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_sleeve(row) for row in rows]

    def update_status(self, *, sleeve_id: int, status: str, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE strategy_sleeves SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, int(sleeve_id)),
        )
        self._conn.commit()

    def update_balances(
        self,
        *,
        sleeve_id: int,
        current_cash: float,
        current_equity: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE strategy_sleeves
            SET current_cash = ?, current_equity = ?, updated_at = ?
            WHERE id = ?
            """,
            (float(current_cash), float(current_equity), updated_at, int(sleeve_id)),
        )
        self._conn.commit()

    def update_trade_universes(
        self,
        *,
        sleeve_id: int,
        trade_universes: str | None,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            "UPDATE strategy_sleeves SET trade_universes = ?, updated_at = ? WHERE id = ?",
            (trade_universes, updated_at, int(sleeve_id)),
        )
        self._conn.commit()

    # --- sleeve_strategy_assignments ---

    def insert_assignment(
        self,
        *,
        sleeve_id: int,
        strategy_name: str,
        param_set_id: int | None,
        effective_from: str,
        effective_to: str | None,
        is_incumbent: int,
        created_at: str,
        updated_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO sleeve_strategy_assignments (
                sleeve_id,
                strategy_name,
                param_set_id,
                effective_from,
                effective_to,
                is_incumbent,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(sleeve_id),
                strategy_name,
                None if param_set_id is None else int(param_set_id),
                effective_from,
                effective_to,
                int(is_incumbent),
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected sleeve_strategy_assignments id after insert.")
        return int(cursor.lastrowid)

    def fetch_active_assignment(self, *, sleeve_id: int) -> SleeveStrategyAssignmentRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM sleeve_strategy_assignments
            WHERE sleeve_id = ?
              AND is_incumbent = 1
              AND effective_to IS NULL
            ORDER BY effective_from DESC, id DESC
            LIMIT 1
            """,
            (int(sleeve_id),),
        ).fetchone()
        return self._row_to_assignment(row) if row is not None else None

    def fetch_assignments(self, *, sleeve_id: int) -> list[SleeveStrategyAssignmentRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sleeve_strategy_assignments
            WHERE sleeve_id = ?
            ORDER BY effective_from DESC, id DESC
            """,
            (int(sleeve_id),),
        ).fetchall()
        return [self._row_to_assignment(row) for row in rows]

    def close_active_assignment(
        self,
        *,
        sleeve_id: int,
        effective_to: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE sleeve_strategy_assignments
            SET is_incumbent = 0,
                effective_to = ?,
                updated_at = ?
            WHERE sleeve_id = ?
              AND is_incumbent = 1
              AND effective_to IS NULL
            """,
            (effective_to, updated_at, int(sleeve_id)),
        )
        self._conn.commit()
