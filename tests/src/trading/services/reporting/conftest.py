from __future__ import annotations

import sqlite3

import pytest

from trading.services.accounts.mutations import create_account, get_account


@pytest.fixture
def reporting_account(conn: sqlite3.Connection) -> sqlite3.Row:
    """Standard reporting account: name='acct_reporting', strategy='Trend', cash=1000."""
    create_account(conn, "acct_reporting", "Trend", 1_000.0, "SPY")
    return get_account(conn, "acct_reporting")
