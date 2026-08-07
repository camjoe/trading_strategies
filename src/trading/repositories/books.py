from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.models.books import BookRecord
from trading.repositories.unit_of_work import commit_unit_of_work


class BookRepository:
    """SQL access for books — the clean-schema execution primitive.

    The one-default-book-per-account invariant is enforced by the partial unique
    index `idx_books_default_per_account`; violations surface as
    sqlite3.IntegrityError.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> BookRecord:
        return BookRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        account_id: int,
        name: str,
        status: str = "active",
        is_default: int = 0,
        start_equity: float,
        current_cash: float,
        current_equity: float,
        # Explicitly unset. Resolving a universe name to symbols is service
        # work (revision 0029), so the repository has no default to offer.
        trade_symbols: str = "[]",
        goal_min_return_pct: float | None = None,
        goal_max_return_pct: float | None = None,
        goal_period: str | None = None,
        learning_enabled: int = 0,
        risk_policy: str = "none",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        option_profit_take_pct: float | None = None,
        option_max_loss_pct: float | None = None,
        trade_size_pct: float | None = None,
        max_position_pct: float | None = None,
        max_trades_per_run: int | None = None,
        instrument_mode: str = "equity",
        option_strike_offset_pct: float | None = None,
        option_min_dte: int | None = None,
        option_max_dte: int | None = None,
        option_type: str | None = None,
        target_delta_min: float | None = None,
        target_delta_max: float | None = None,
        max_premium_per_trade: float | None = None,
        max_contracts_per_trade: int | None = None,
        iv_rank_min: float | None = None,
        iv_rank_max: float | None = None,
        roll_dte_threshold: int | None = None,
        created_at: str,
        updated_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO books (
                account_id, name, status, is_default, start_equity, current_cash,
                current_equity, trade_symbols, goal_min_return_pct,
                goal_max_return_pct, goal_period, learning_enabled, risk_policy,
                stop_loss_pct, take_profit_pct, option_profit_take_pct, option_max_loss_pct,
                trade_size_pct, max_position_pct, max_trades_per_run,
                instrument_mode, option_strike_offset_pct, option_min_dte,
                option_max_dte, option_type, target_delta_min, target_delta_max,
                max_premium_per_trade, max_contracts_per_trade, iv_rank_min,
                iv_rank_max, roll_dte_threshold, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                name,
                status,
                int(is_default),
                float(start_equity),
                float(current_cash),
                float(current_equity),
                trade_symbols,
                goal_min_return_pct,
                goal_max_return_pct,
                goal_period,
                int(learning_enabled),
                risk_policy,
                stop_loss_pct,
                take_profit_pct,
                option_profit_take_pct,
                option_max_loss_pct,
                trade_size_pct,
                max_position_pct,
                max_trades_per_run,
                instrument_mode,
                option_strike_offset_pct,
                option_min_dte,
                option_max_dte,
                option_type,
                target_delta_min,
                target_delta_max,
                max_premium_per_trade,
                max_contracts_per_trade,
                iv_rank_min,
                iv_rank_max,
                roll_dte_threshold,
                created_at,
                updated_at,
            ),
        )
        book_id = int(cursor.lastrowid or 0)
        self._record_universe_history(book_id=book_id, trade_symbols=trade_symbols, effective_from=created_at)
        commit_unit_of_work(self._conn)
        return book_id

    def _record_universe_history(self, *, book_id: int, trade_symbols: str, effective_from: str) -> None:
        """Close the open universe-history row (if any) and open a new one."""
        self._conn.execute(
            "UPDATE book_universe_history SET effective_to = ? WHERE book_id = ? AND effective_to IS NULL",
            (effective_from, int(book_id)),
        )
        self._conn.execute(
            """
            INSERT INTO book_universe_history (book_id, trade_symbols, effective_from, effective_to)
            VALUES (?, ?, ?, NULL)
            """,
            (int(book_id), trade_symbols, effective_from),
        )

    def update_settings_columns(self, *, book_id: int, updates: list[str], params: list[object]) -> None:
        """Apply pre-built ``column = ?`` update fragments to one book."""
        self._conn.execute(
            f"UPDATE books SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
            (*params, utc_now_iso(), int(book_id)),
        )
        commit_unit_of_work(self._conn)

    def fetch_by_id(self, *, book_id: int) -> BookRecord | None:
        row = self._conn.execute(
            "SELECT * FROM books WHERE id = ?",
            (int(book_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_for_account(self, *, account_id: int) -> list[BookRecord]:
        rows = self._conn.execute(
            "SELECT * FROM books WHERE account_id = ? ORDER BY id ASC",
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_default_for_account(self, *, account_id: int) -> BookRecord | None:
        row = self._conn.execute(
            "SELECT * FROM books WHERE account_id = ? AND is_default = 1",
            (int(account_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def update_status(self, *, book_id: int, status: str, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE books SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, int(book_id)),
        )
        commit_unit_of_work(self._conn)

    def update_trade_symbols(self, *, book_id: int, trade_symbols: str, updated_at: str) -> None:
        """Set the book's universes and record the change in the history table."""
        self._conn.execute(
            "UPDATE books SET trade_symbols = ?, updated_at = ? WHERE id = ?",
            (trade_symbols, updated_at, int(book_id)),
        )
        self._record_universe_history(book_id=book_id, trade_symbols=trade_symbols, effective_from=updated_at)
        commit_unit_of_work(self._conn)

    def update_balances(
        self,
        *,
        book_id: int,
        current_cash: float,
        current_equity: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE books
            SET current_cash = ?, current_equity = ?, updated_at = ?
            WHERE id = ?
            """,
            (float(current_cash), float(current_equity), updated_at, int(book_id)),
        )
        commit_unit_of_work(self._conn)
