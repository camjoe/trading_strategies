from __future__ import annotations

import sqlite3

from trading.models.sleeve_fill_record import SleeveFillRecord
from trading.models.sleeve_order_record import SleeveOrderRecord


class SleeveOrderRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_order(self, row: sqlite3.Row) -> SleeveOrderRecord:
        return SleeveOrderRecord.from_mapping(dict(row))

    def _row_to_fill(self, row: sqlite3.Row) -> SleeveFillRecord:
        return SleeveFillRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        account_id: int,
        sleeve_id: int,
        strategy_name: str,
        param_set_id: int | None,
        rotation_decision_id: int | None,
        broker_order_id: str | None,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        time_in_force: str,
        requested_price: float,
        status: str,
        config_version: str | None,
        submitted_at: str,
        updated_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO sleeve_orders (
                account_id,
                sleeve_id,
                strategy_name,
                param_set_id,
                rotation_decision_id,
                broker_order_id,
                symbol,
                side,
                qty,
                order_type,
                time_in_force,
                requested_price,
                status,
                config_version,
                submitted_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                int(sleeve_id),
                strategy_name,
                None if param_set_id is None else int(param_set_id),
                None if rotation_decision_id is None else int(rotation_decision_id),
                broker_order_id,
                symbol,
                side,
                float(qty),
                order_type,
                time_in_force,
                float(requested_price),
                status,
                config_version,
                submitted_at,
                updated_at,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected sleeve_orders id after insert.")
        return int(cursor.lastrowid)

    def attach_broker_order_id(
        self,
        *,
        sleeve_order_id: int,
        broker_order_id: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            "UPDATE sleeve_orders SET broker_order_id = ?, updated_at = ? WHERE id = ?",
            (broker_order_id, updated_at, int(sleeve_order_id)),
        )
        self._conn.commit()

    def update_status(self, *, sleeve_order_id: int, status: str, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE sleeve_orders SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, int(sleeve_order_id)),
        )
        self._conn.commit()

    def fetch_by_id(self, *, sleeve_order_id: int) -> SleeveOrderRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sleeve_orders WHERE id = ?",
            (int(sleeve_order_id),),
        ).fetchone()
        return self._row_to_order(row) if row is not None else None

    def fetch_by_broker_order_id(
        self,
        *,
        account_id: int,
        broker_order_id: str,
    ) -> SleeveOrderRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM sleeve_orders
            WHERE account_id = ? AND broker_order_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(account_id), broker_order_id),
        ).fetchone()
        return self._row_to_order(row) if row is not None else None

    def fetch_for_sleeve(self, *, sleeve_id: int) -> list[SleeveOrderRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sleeve_orders
            WHERE sleeve_id = ?
            ORDER BY submitted_at DESC, id DESC
            """,
            (int(sleeve_id),),
        ).fetchall()
        return [self._row_to_order(row) for row in rows]

    def fetch_open_for_account(self, *, account_id: int) -> list[SleeveOrderRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sleeve_orders
            WHERE account_id = ?
              AND status NOT IN ('Filled', 'Cancelled', 'Rejected', 'FILLED', 'CANCELLED', 'REJECTED')
            ORDER BY submitted_at ASC, id ASC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_order(row) for row in rows]

    def insert_fill(
        self,
        *,
        sleeve_order_id: int,
        sleeve_id: int,
        broker_fill_id: str | None,
        exec_id: str | None,
        symbol: str,
        filled_qty: float,
        fill_price: float,
        commission: float,
        fill_time: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO sleeve_fills (
                sleeve_order_id,
                sleeve_id,
                broker_fill_id,
                exec_id,
                symbol,
                filled_qty,
                fill_price,
                commission,
                fill_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(sleeve_order_id),
                int(sleeve_id),
                broker_fill_id,
                exec_id,
                symbol,
                float(filled_qty),
                float(fill_price),
                float(commission),
                fill_time,
            ),
        )
        self._conn.commit()

    def fetch_fills_for_order(self, *, sleeve_order_id: int) -> list[SleeveFillRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sleeve_fills
            WHERE sleeve_order_id = ?
            ORDER BY fill_time ASC, id ASC
            """,
            (int(sleeve_order_id),),
        ).fetchall()
        return [self._row_to_fill(row) for row in rows]
