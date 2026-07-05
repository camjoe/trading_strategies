"""Bridging helpers for the P3 book-keyed tables during the legacy window.

Until P4's converged services own the writers, book-keyed storage is reached
from the legacy access paths through three idempotent resolutions:

- account → its default book (created bare on first write; settings rows are
  intentionally absent — missing row means code defaults, D4),
- legacy sleeve → a bridging book named after the sleeve,
- strategy label → a `strategies` row (created as a draft when the catalog
  has no row for the label yet).

All three retire with P4.
"""

from __future__ import annotations

import sqlite3


def default_book_id(conn: sqlite3.Connection, account_id: int) -> int:
    """Resolve (bootstrapping if needed) the account's default book id."""
    row = conn.execute(
        "SELECT id FROM books WHERE account_id = ? AND is_default = 1",
        (int(account_id),),
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash,
            current_equity, trade_universes, goal_min_return_pct,
            goal_max_return_pct, goal_period, created_at, updated_at
        )
        SELECT id, 'default', 'active', 1, initial_cash, initial_cash, initial_cash,
               trade_universes, goal_min_return_pct, goal_max_return_pct, goal_period,
               created_at, created_at
        FROM accounts WHERE id = ?
        """,
        (int(account_id),),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"Account {account_id} does not exist; cannot resolve its default book.")
    return int(cursor.lastrowid or 0)


def book_id_for_sleeve(conn: sqlite3.Connection, sleeve_id: int, *, create: bool) -> int | None:
    """Resolve a legacy sleeve to its bridging book (same account, sleeve's name)."""
    sleeve = conn.execute(
        "SELECT account_id, name, start_equity, current_cash, current_equity, created_at "
        "FROM strategy_sleeves WHERE id = ?",
        (int(sleeve_id),),
    ).fetchone()
    if sleeve is None:
        raise LookupError(f"Sleeve {sleeve_id} does not exist; cannot resolve its book.")
    row = conn.execute(
        "SELECT id FROM books WHERE account_id = ? AND name = ?",
        (int(sleeve["account_id"]), str(sleeve["name"])),
    ).fetchone()
    if row is not None:
        return int(row[0])
    if not create:
        return None
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash,
            current_equity, created_at, updated_at
        )
        VALUES (?, ?, 'active', 0, ?, ?, ?, ?, ?)
        """,
        (
            int(sleeve["account_id"]),
            str(sleeve["name"]),
            float(sleeve["start_equity"]),
            float(sleeve["current_cash"]),
            float(sleeve["current_equity"]),
            str(sleeve["created_at"]),
            str(sleeve["created_at"]),
        ),
    )
    return int(cursor.lastrowid or 0)


_ORDER_STATUS_VOCAB = {"submitted", "partially_filled", "filled", "rejected", "cancelled"}


def order_id_for_broker_order(conn: sqlite3.Connection, broker_order_id: str) -> int:
    """Resolve a legacy broker order to its clean-schema orders row, mirroring on demand.

    Legacy statuses outside the clean vocabulary (pending/accepted) map to
    'submitted'.
    """
    row = conn.execute(
        "SELECT id FROM orders WHERE broker_order_id = ?",
        (broker_order_id,),
    ).fetchone()
    if row is not None:
        return int(row[0])
    legacy = conn.execute(
        "SELECT * FROM broker_orders WHERE broker_order_id = ?",
        (broker_order_id,),
    ).fetchone()
    if legacy is None:
        raise LookupError(f"Broker order {broker_order_id!r} does not exist; cannot mirror it into orders.")
    status = str(legacy["status"]).strip().lower()
    if status not in _ORDER_STATUS_VOCAB:
        status = "submitted"
    book_id = default_book_id(conn, int(legacy["account_id"]))
    cursor = conn.execute(
        """
        INSERT INTO orders (
            book_id, account_id, broker_order_id, symbol, side, qty, order_type,
            time_in_force, requested_price, status, filled_qty, avg_fill_price,
            commission, submitted_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book_id,
            int(legacy["account_id"]),
            broker_order_id,
            str(legacy["ticker"]),
            str(legacy["side"]),
            float(legacy["qty"]),
            str(legacy["order_type"]),
            str(legacy["time_in_force"]),
            legacy["requested_price"],
            status,
            float(legacy["filled_qty"]),
            legacy["avg_fill_price"],
            float(legacy["commission"]),
            str(legacy["submitted_at"]),
            str(legacy["updated_at"]),
        ),
    )
    return int(cursor.lastrowid or 0)


def strategy_id_for_label(
    conn: sqlite3.Connection,
    label: str | None,
    *,
    now_iso: str,
    create: bool = True,
) -> int | None:
    """Resolve a legacy strategy label to a strategies row id (draft-created if unknown)."""
    if label is None or not label.strip():
        return None
    key = label.strip().lower()
    row = conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (key,)).fetchone()
    if row is not None:
        return int(row[0])
    if not create:
        return None
    cursor = conn.execute(
        """
        INSERT INTO strategies (
            strategy_key, primitive, params_json, style, status, enabled, created_at, updated_at
        )
        VALUES (?, ?, '{}', 'neutral', 'draft', 1, ?, ?)
        """,
        (key, key, now_iso, now_iso),
    )
    return int(cursor.lastrowid or 0)
