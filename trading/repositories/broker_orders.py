from __future__ import annotations

import sqlite3

from trading.database.sql_helpers import in_placeholders
from trading.models.broker_order import BrokerOrder, OrderFill, OrderStatus
from trading.models.broker_order_record import BrokerOrderRecord


class BrokerOrderRepository:

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> BrokerOrderRecord:
        return BrokerOrderRecord.from_mapping(dict(row))

    def insert_order(self, order: BrokerOrder) -> None:
        self._conn.execute(
            """
            INSERT INTO broker_orders (
                account_id, broker_order_id, ticker, side, qty,
                order_type, time_in_force, requested_price, status,
                filled_qty, avg_fill_price, commission, submitted_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.account_id,
                order.broker_order_id,
                order.ticker,
                order.side,
                order.qty,
                order.order_type.value,
                order.time_in_force.value,
                order.price,
                order.status.value,
                order.filled_qty,
                order.avg_fill_price,
                order.commission,
                order.submitted_at,
                order.updated_at,
            ),
        )
        self._conn.commit()

    def insert_fill(self, broker_order_id: str, fill: OrderFill) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO order_fills
                (broker_order_id, filled_qty, fill_price, fill_time, commission, exec_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (broker_order_id, fill.filled_qty, fill.fill_price, fill.fill_time, fill.commission, fill.exec_id),
        )
        self._conn.commit()

    def update_status(
        self,
        *,
        broker_order_id: str,
        status: OrderStatus,
        filled_qty: float,
        avg_fill_price: float | None,
        commission: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE broker_orders
            SET status = ?, filled_qty = ?, avg_fill_price = ?, commission = ?, updated_at = ?
            WHERE broker_order_id = ?
            """,
            (status.value, filled_qty, avg_fill_price, commission, updated_at, broker_order_id),
        )
        self._conn.commit()

    def fetch_for_account(self, *, account_id: int) -> list[BrokerOrderRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM broker_orders
            WHERE account_id = ?
            ORDER BY submitted_at, id
            """,
            (account_id,),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_open(self, *, account_id: int) -> list[BrokerOrderRecord]:
        terminal = (
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value,
        )
        placeholders = in_placeholders(terminal)
        rows = self._conn.execute(
            f"""
            SELECT * FROM broker_orders
            WHERE account_id = ? AND status NOT IN ({placeholders})
            ORDER BY submitted_at, id
            """,
            (account_id, *terminal),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
