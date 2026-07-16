"""Clean strategy-book schema: tables, invariants, and FK enforcement.

Covers the additive clean-schema tables. Colliding legacy tables
(equity_snapshots, daily_metrics, rotation_decisions, order_fills) were swapped
to their clean shapes separately.
"""

from pathlib import Path

import pytest
import sqlite3

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.connection import ensure_db
from tests.support.db_schema import build_db_at_head

NEW_TABLES = {
    "books",
    "strategies",
    "feature_providers",
    "book_execution_settings",
    "book_option_settings",
    "book_rotation_settings",
    "book_strategy_assignments",
    "orders",
    "positions",
    "ledger",
    "risk_snapshots",
    "risk_decisions",
}


@pytest.fixture
def conn(tmp_path: Path):
    original = get_backend()
    set_backend(SQLiteBackend(build_db_at_head(tmp_path / "paper_trading.db")))
    connection = ensure_db()
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)


def _insert_account(conn, name: str = "acct_books") -> int:
    cursor = conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at) VALUES (?, 'trend', 5000, '2026-07-03T00:00:00Z')",
        (name,),
    )
    return int(cursor.lastrowid)


def _insert_book(conn, account_id: int, name: str = "default", is_default: int = 1) -> int:
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash,
            current_equity, created_at, updated_at
        ) VALUES (?, ?, 'active', ?, 5000, 5000, 5000, '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
        """,
        (account_id, name, is_default),
    )
    return int(cursor.lastrowid)


def _insert_strategy(conn, key: str = "trend") -> int:
    cursor = conn.execute(
        """
        INSERT INTO strategies (
            strategy_key, primitive, params_json, style, status, enabled, created_at, updated_at
        ) VALUES (?, 'trend', '{"fast_window": 10}', 'trend', 'draft', 1,
                  '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
        """,
        (key,),
    )
    return int(cursor.lastrowid)


def test_fresh_init_creates_clean_schema_tables(conn) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {str(row["name"]) for row in rows}
    assert NEW_TABLES <= names


def test_accounts_gains_custody_columns(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
    assert "base_ccy" in columns
    assert "updated_at" in columns


def test_one_default_book_per_account_enforced(conn) -> None:
    account_id = _insert_account(conn)
    _insert_book(conn, account_id, name="default", is_default=1)
    # A second non-default book is fine.
    _insert_book(conn, account_id, name="second", is_default=0)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_book(conn, account_id, name="third", is_default=1)


def test_one_open_assignment_per_book_enforced(conn) -> None:
    account_id = _insert_account(conn)
    book_id = _insert_book(conn, account_id)
    strategy_id = _insert_strategy(conn)

    def _insert_assignment(effective_to: str | None) -> None:
        conn.execute(
            """
            INSERT INTO book_strategy_assignments (
                book_id, strategy_id, effective_from, effective_to, is_incumbent,
                created_at, updated_at
            ) VALUES (?, ?, '2026-07-03T00:00:00Z', ?, 1,
                      '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
            """,
            (book_id, strategy_id, effective_to),
        )

    _insert_assignment(effective_to="2026-07-04T00:00:00Z")  # closed — fine
    _insert_assignment(effective_to=None)  # the open incumbent

    with pytest.raises(sqlite3.IntegrityError):
        _insert_assignment(effective_to=None)  # second open assignment


def test_foreign_keys_are_enforced(conn) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert_book(conn, account_id=999_999)


def test_deleting_account_cascades_to_books_and_settings(conn) -> None:
    account_id = _insert_account(conn)
    book_id = _insert_book(conn, account_id)
    conn.execute(
        """
        INSERT INTO book_execution_settings (book_id, created_at, updated_at)
        VALUES (?, '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
        """,
        (book_id,),
    )

    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM book_execution_settings").fetchone()[0] == 0


def test_strategies_status_vocabulary_enforced(conn) -> None:
    _insert_strategy(conn, key="valid")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO strategies (
                strategy_key, primitive, params_json, style, status, enabled, created_at, updated_at
            ) VALUES ('bad_status', 'trend', '{}', 'trend', 'archived', 1,
                      '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
            """
        )
