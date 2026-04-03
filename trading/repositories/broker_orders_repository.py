"""Repository for broker_orders and order_fills tables.

Follows the repository naming convention:
  - reads:  fetch_*
  - writes: insert_*, update_*
"""
from __future__ import annotations

import sqlite3

from trading.brokers.base import BrokerOrder, OrderFill, OrderStatus


def insert_broker_order(conn: sqlite3.Connection, order: BrokerOrder) -> None:
    """Persist a broker order record (any status)."""
    conn.execute(
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
    conn.commit()


def insert_order_fill(conn: sqlite3.Connection, broker_order_id: str, fill: OrderFill) -> None:
    """Persist a single execution report for an existing broker order."""
    conn.execute(
        """
        INSERT INTO order_fills (broker_order_id, filled_qty, fill_price, fill_time, commission)
        VALUES (?, ?, ?, ?, ?)
        """,
        (broker_order_id, fill.filled_qty, fill.fill_price, fill.fill_time, fill.commission),
    )
    conn.commit()


def update_broker_order_status(
    conn: sqlite3.Connection,
    broker_order_id: str,
    status: OrderStatus,
    filled_qty: float,
    avg_fill_price: float | None,
    commission: float,
    updated_at: str,
) -> None:
    """Update mutable fields on an existing broker order after a fill or cancellation."""
    conn.execute(
        """
        UPDATE broker_orders
        SET status = ?, filled_qty = ?, avg_fill_price = ?, commission = ?, updated_at = ?
        WHERE broker_order_id = ?
        """,
        (status.value, filled_qty, avg_fill_price, commission, updated_at, broker_order_id),
    )
    conn.commit()


def fetch_broker_orders_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> list[sqlite3.Row]:
    """Return all broker orders for *account_id*, ordered by submission time."""
    return conn.execute(
        """
        SELECT * FROM broker_orders
        WHERE account_id = ?
        ORDER BY submitted_at, id
        """,
        (account_id,),
    ).fetchall()


def fetch_open_broker_orders(conn: sqlite3.Connection, *, account_id: int) -> list[sqlite3.Row]:
    """Return orders not yet in a terminal state (FILLED / CANCELLED / REJECTED)."""
    terminal = (
        OrderStatus.FILLED.value,
        OrderStatus.CANCELLED.value,
        OrderStatus.REJECTED.value,
    )
    placeholders = ", ".join("?" * len(terminal))
    return conn.execute(
        f"""
        SELECT * FROM broker_orders
        WHERE account_id = ? AND status NOT IN ({placeholders})
        ORDER BY submitted_at, id
        """,
        (account_id, *terminal),
    ).fetchall()
