from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from trading.services.accounts import create_account, get_account
from tests.support.repositories import insert_repository_account
from tests.support.books import insert_test_book


@pytest.fixture
def reporting_account(conn: sqlite3.Connection) -> sqlite3.Row:
    """Standard reporting account: name='acct_reporting', strategy='Trend', cash=1000."""
    create_account(conn, "acct_reporting", "Trend", 1_000.0, "SPY")
    return get_account(conn, "acct_reporting")


@pytest.fixture
def report_env(conn) -> SimpleNamespace:
    """Account + book ready for daily-report tests."""
    account_name = "report_acct"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = insert_test_book(
        conn,
        account_id=account_id,
        name="book_a",
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    return SimpleNamespace(account_id=account_id, account_name=account_name, book_id=book_id)
