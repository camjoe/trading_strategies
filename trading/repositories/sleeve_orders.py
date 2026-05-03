from __future__ import annotations

import sqlite3


def insert_sleeve_order(
    conn: sqlite3.Connection,
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
    cursor = conn.execute(
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
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected sleeve_orders id after insert.")
    return int(cursor.lastrowid)


def attach_sleeve_order_broker_order_id(
    conn: sqlite3.Connection,
    *,
    sleeve_order_id: int,
    broker_order_id: str,
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE sleeve_orders
        SET broker_order_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (broker_order_id, updated_at, int(sleeve_order_id)),
    )
    conn.commit()


def update_sleeve_order_status(
    conn: sqlite3.Connection,
    *,
    sleeve_order_id: int,
    status: str,
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE sleeve_orders
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, updated_at, int(sleeve_order_id)),
    )
    conn.commit()


def fetch_sleeve_order_by_id(
    conn: sqlite3.Connection,
    *,
    sleeve_order_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_orders
        WHERE id = ?
        """,
        (int(sleeve_order_id),),
    ).fetchone()


def fetch_sleeve_orders_for_sleeve(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_orders
        WHERE sleeve_id = ?
        ORDER BY submitted_at DESC, id DESC
        """,
        (int(sleeve_id),),
    ).fetchall()


def fetch_open_sleeve_orders_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_orders
        WHERE account_id = ?
          AND status NOT IN ('Filled', 'Cancelled', 'Rejected', 'FILLED', 'CANCELLED', 'REJECTED')
        ORDER BY submitted_at ASC, id ASC
        """,
        (int(account_id),),
    ).fetchall()


def insert_sleeve_fill(
    conn: sqlite3.Connection,
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
    conn.execute(
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
    conn.commit()


def fetch_sleeve_fills_for_order(
    conn: sqlite3.Connection,
    *,
    sleeve_order_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_fills
        WHERE sleeve_order_id = ?
        ORDER BY fill_time ASC, id ASC
        """,
        (int(sleeve_order_id),),
    ).fetchall()
