from __future__ import annotations

import sqlite3

from trading.repositories.unit_of_work import maybe_commit
from trading.models.orders.order_record import OrderRecord


class BookAccountMismatchError(ValueError):
    """Raised when an order's book does not belong to its account (invariant 4)."""


class OrderRepository:
    """SQL access for the clean-schema orders table (unifies broker + book orders).

    Order ↔ book ↔ account integrity (invariant 4) cannot be expressed as a cheap
    SQLite constraint, so `insert` verifies the book belongs to the account.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> OrderRecord:
        return OrderRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        book_id: int,
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
        status_reason: str | None = None,
    ) -> int:
        owner = self._conn.execute(
            "SELECT account_id FROM books WHERE id = ?",
            (int(book_id),),
        ).fetchone()
        if owner is None or int(owner[0]) != int(account_id):
            raise BookAccountMismatchError(
                f"Book {book_id} does not belong to account {account_id}; refusing to insert order."
            )
        cursor = self._conn.execute(
            """
            INSERT INTO orders (
                book_id, account_id, strategy_id, rotation_decision_id, broker_order_id,
                symbol, side, qty, order_type, time_in_force, requested_price, status,
                filled_qty, avg_fill_price, commission, submitted_at, updated_at, status_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(book_id),
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
                status_reason,
            ),
        )
        maybe_commit(self._conn)
        return int(cursor.lastrowid or 0)

    def insert_fill(
        self,
        *,
        order_id: int,
        filled_qty: float,
        fill_price: float,
        fill_time: str,
        commission: float = 0.0,
        exec_id: str | None = None,
    ) -> None:
        # Fills key directly on the clean order_id (the execution service owns it).
        # OR IGNORE + UNIQUE(order_id, exec_id) makes replayed execution reports idempotent.
        self._conn.execute(
            """
            INSERT OR IGNORE INTO order_fills
                (order_id, exec_id, filled_qty, fill_price, commission, fill_time)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(order_id),
                exec_id,
                float(filled_qty),
                float(fill_price),
                float(commission),
                fill_time,
            ),
        )
        maybe_commit(self._conn)

    def fetch_fill_exec_ids(self, *, order_id: int) -> set[str]:
        """Return the non-null exec_ids already recorded for an order (fill dedup)."""
        rows = self._conn.execute(
            "SELECT exec_id FROM order_fills WHERE order_id = ? AND exec_id IS NOT NULL",
            (int(order_id),),
        ).fetchall()
        return {str(row[0]) for row in rows}

    def fetch_fill_events_for_account(self, *, account_id: int) -> list[sqlite3.Row]:
        """Fill executions for the account's orders as trade-shaped rows, oldest first.

        Feeds the account-state replay (``trading.services.accounting``): the
        keys mirror the retired ``trades`` rows so the pure replay math is
        unchanged.
        """
        return self._conn.execute(
            """
            SELECT o.symbol AS ticker, o.side AS side, f.filled_qty AS qty,
                   f.fill_price AS price, f.commission AS fee,
                   f.fill_time AS trade_time, f.order_id AS order_id
            FROM order_fills f
            JOIN orders o ON o.id = f.order_id
            WHERE o.account_id = ?
            ORDER BY f.fill_time ASC, f.id ASC
            """,
            (int(account_id),),
        ).fetchall()

    def fetch_fill_count_between(self, *, start_iso: str, end_iso: str) -> int:
        """Global fill count in a time window (runtime trade throttles)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM order_fills WHERE fill_time >= ? AND fill_time <= ?",
            (start_iso, end_iso),
        ).fetchone()
        return 0 if row is None else int(row[0])

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

    def fetch_for_book(self, *, book_id: int) -> list[OrderRecord]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE book_id = ? ORDER BY submitted_at DESC, id DESC",
            (int(book_id),),
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
        status_reason: str | None = None,
    ) -> None:
        # status_reason is COALESCEd: a later poll without a reason must not erase
        # one an earlier terminal update recorded.
        self._conn.execute(
            """
            UPDATE orders
            SET status = ?,
                filled_qty = COALESCE(?, filled_qty),
                avg_fill_price = COALESCE(?, avg_fill_price),
                status_reason = COALESCE(?, status_reason),
                updated_at = ?
            WHERE id = ?
            """,
            (status, filled_qty, avg_fill_price, status_reason, updated_at, int(order_id)),
        )
        maybe_commit(self._conn)
