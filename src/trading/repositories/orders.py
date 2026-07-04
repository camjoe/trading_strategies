from __future__ import annotations

import sqlite3

from trading.models.orders.order_record import OrderRecord


class OrderUnitAccountMismatchError(ValueError):
    """Raised when an order's unit does not belong to its account (invariant 4)."""


class OrderRepository:
    """SQL access for the clean-schema orders table (unifies broker + sleeve orders).

    Order ↔ unit ↔ account integrity (invariant 4) cannot be expressed as a cheap
    SQLite constraint, so `insert` verifies the unit belongs to the account.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> OrderRecord:
        return OrderRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        unit_id: int,
        account_id: int,
        strategy_id: int | None = None,
        rotation_decision_id: int | None = None,
        broker_order_id: str | None = None,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "market",
        time_in_force: str = "day",
        requested_price: float | None = None,
        status: str,
        filled_qty: float = 0.0,
        avg_fill_price: float | None = None,
        commission: float = 0.0,
        submitted_at: str,
        updated_at: str,
    ) -> int:
        owner = self._conn.execute(
            "SELECT account_id FROM trading_units WHERE id = ?",
            (int(unit_id),),
        ).fetchone()
        if owner is None or int(owner[0]) != int(account_id):
            raise OrderUnitAccountMismatchError(
                f"Unit {unit_id} does not belong to account {account_id}; refusing to insert order."
            )
        cursor = self._conn.execute(
            """
            INSERT INTO orders (
                unit_id, account_id, strategy_id, rotation_decision_id, broker_order_id,
                symbol, side, qty, order_type, time_in_force, requested_price, status,
                filled_qty, avg_fill_price, commission, submitted_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(unit_id),
                int(account_id),
                strategy_id,
                rotation_decision_id,
                broker_order_id,
                symbol,
                side,
                float(qty),
                order_type,
                time_in_force,
                requested_price,
                status,
                float(filled_qty),
                avg_fill_price,
                float(commission),
                submitted_at,
                updated_at,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def fetch_by_id(self, *, order_id: int) -> OrderRecord | None:
        row = self._conn.execute(
            "SELECT * FROM orders WHERE id = ?",
            (int(order_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_by_broker_order_id(self, *, account_id: int, broker_order_id: str) -> OrderRecord | None:
        row = self._conn.execute(
            "SELECT * FROM orders WHERE account_id = ? AND broker_order_id = ?",
            (int(account_id), broker_order_id),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_open_for_account(self, *, account_id: int) -> list[OrderRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM orders
            WHERE account_id = ? AND status IN ('submitted', 'partially_filled')
            ORDER BY submitted_at DESC, id DESC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_unit(self, *, unit_id: int) -> list[OrderRecord]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE unit_id = ? ORDER BY submitted_at DESC, id DESC",
            (int(unit_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_status(
        self,
        *,
        order_id: int,
        status: str,
        filled_qty: float | None = None,
        avg_fill_price: float | None = None,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE orders
            SET status = ?,
                filled_qty = COALESCE(?, filled_qty),
                avg_fill_price = COALESCE(?, avg_fill_price),
                updated_at = ?
            WHERE id = ?
            """,
            (status, filled_qty, avg_fill_price, updated_at, int(order_id)),
        )
        self._conn.commit()
