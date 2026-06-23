from __future__ import annotations

import sqlite3

import pytest

from trading.services.accounts import create_account


@pytest.fixture
def promotion_account(conn: sqlite3.Connection) -> None:
    """Insert the canonical promotion test account into the test database.

    Tests that exercise promotion actions require an account row to exist.
    This fixture inserts ``acct_service`` with strategy ``trend_v1`` and
    commits, matching the inline setup previously repeated in each test.
    """
    create_account(conn, "acct_service", "trend_v1", 1_000.0, "SPY")
