"""Clean strategy-book schema: tables, invariants, and FK enforcement.

Covers the additive clean-schema tables. Colliding legacy tables
(equity_snapshots, daily_metrics, rotation_decisions, order_fills) were swapped
to their clean shapes separately.
"""

import sqlite3

import pytest

NEW_TABLES = {
    "books",
    "strategies",
    "feature_providers",
    "book_rotation_settings",
    "book_strategy_history",
    "orders",
    "positions",
    "ledger",
    "risk_snapshots",
    "risk_decisions",
}


def _insert_account(conn, name: str = "acct_books") -> int:
    cursor = conn.execute(
        "INSERT INTO accounts (name, initial_cash, created_at, updated_at) "
        "VALUES (?, 5000, '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')",
        (name,),
    )
    return int(cursor.lastrowid)


def _insert_book(conn, account_id: int, name: str = "default", is_default: int = 1) -> int:
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash,
            current_equity, trade_symbols, created_at, updated_at
        ) VALUES (?, ?, 'active', ?, 5000, 5000, 5000, '["AAPL","MSFT"]', '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
        """,
        (account_id, name, is_default),
    )
    return int(cursor.lastrowid)


def _insert_strategy(conn, key: str = "trend") -> int:
    cursor = conn.execute(
        """
        INSERT INTO strategies (
            strategy_key, primitive, params_json, status, enabled, created_at, updated_at
        ) VALUES (?, 'trend', '{"fast_window": 10}', 'draft', 1,
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
            INSERT INTO book_strategy_history (
                book_id, strategy_id, effective_from, effective_to,
                created_at, updated_at
            ) VALUES (?, ?, '2026-07-03T00:00:00Z', ?,
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
    # Execution/option settings live on books (revisions 0004/0005); rotation
    # settings remain the 1:1 settings table riding the cascade.
    conn.execute(
        """
        INSERT INTO book_rotation_settings (book_id, created_at, updated_at)
        VALUES (?, '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
        """,
        (book_id,),
    )

    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM book_rotation_settings").fetchone()[0] == 0


def test_strategies_status_vocabulary_enforced(conn) -> None:
    _insert_strategy(conn, key="valid")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO strategies (
                strategy_key, primitive, params_json, status, enabled, created_at, updated_at
            ) VALUES ('bad_status', 'trend', '{}', 'archived', 1,
                      '2026-07-03T00:00:00Z', '2026-07-03T00:00:00Z')
            """
        )
