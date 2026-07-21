"""apply_book_fill is atomic: a mid-sequence failure leaves no partial state.

Regression guard for the execution/accounting-quartet review finding — before
the unit-of-work wrapper, each repository write self-committed, so a crash
between the fill/position/ledger writes and the balance update left the book's
projections permanently inconsistent (and exec_id dedup would skip the fill on
re-run, never applying its cash effect).
"""

from __future__ import annotations

import sqlite3

import pytest

from trading.repositories.books import BookRepository
from trading.services.execution import submission
from trading.services.execution.submission import apply_book_fill
from tests.support.repositories import insert_repository_account


@pytest.fixture
def book_env(conn):
    account_id = insert_repository_account(conn, name="atomic_acct")
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name="default",
        is_default=1,
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-07-21T00:00:00Z",
        updated_at="2026-07-21T00:00:00Z",
    )
    return account_id, book_id


def _position_count(conn: sqlite3.Connection, book_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM positions WHERE book_id = ?", (book_id,)).fetchone()[0])


def _ledger_count(conn: sqlite3.Connection, book_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM ledger WHERE book_id = ?", (book_id,)).fetchone()[0])


def test_apply_book_fill_commits_position_ledger_and_balances(conn, book_env) -> None:
    _account_id, book_id = book_env

    apply_book_fill(
        conn,
        book_id=book_id,
        order_id=1,
        side="buy",
        symbol="AAPL",
        fill_qty=10.0,
        fill_price=100.0,
        transaction_cost=5.0,
        fill_time="2026-07-21T10:00:00Z",
    )

    assert _position_count(conn, book_id) == 1
    assert _ledger_count(conn, book_id) == 2  # gross trade + fee
    cash = conn.execute("SELECT current_cash FROM books WHERE id = ?", (book_id,)).fetchone()[0]
    assert cash == pytest.approx(10_000.0 - 1_000.0 - 5.0)


def test_failure_mid_sequence_rolls_back_the_whole_fill(conn, book_env, monkeypatch) -> None:
    _account_id, book_id = book_env

    def _boom(self, **kwargs):
        raise RuntimeError("simulated crash after position and ledger writes")

    # update_balances is the last write in apply_book_fill; failing it exercises
    # the case where position and ledger rows are already written in-transaction.
    monkeypatch.setattr(BookRepository, "update_balances", _boom)

    with pytest.raises(RuntimeError):
        apply_book_fill(
            conn,
            book_id=book_id,
            order_id=1,
            side="buy",
            symbol="AAPL",
            fill_qty=10.0,
            fill_price=100.0,
            transaction_cost=5.0,
            fill_time="2026-07-21T10:00:00Z",
        )

    # Nothing partial survived: no position, no ledger entries, cash untouched.
    assert _position_count(conn, book_id) == 0
    assert _ledger_count(conn, book_id) == 0
    cash = conn.execute("SELECT current_cash FROM books WHERE id = ?", (book_id,)).fetchone()[0]
    assert cash == pytest.approx(10_000.0)


def test_submission_module_exposes_apply_book_fill() -> None:
    # Guard the import path the reconciliation service depends on.
    assert hasattr(submission, "apply_book_fill")
