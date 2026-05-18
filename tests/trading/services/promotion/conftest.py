from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def promotion_account(conn: sqlite3.Connection) -> None:
    """Insert the canonical promotion test account into the test database.

    Tests that exercise promotion actions require an account row to exist.
    This fixture inserts ``acct_service`` with strategy ``trend_v1`` and
    commits, matching the inline setup previously repeated in each test.
    """
    conn.execute(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (1, 'acct_service', 'trend_v1', 1000, 'SPY', '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()
