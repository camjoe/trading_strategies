from __future__ import annotations

import sqlite3

import pytest

from trading.services.accounts.mutations import create_account, get_account


@pytest.fixture
def accounting_account(conn: sqlite3.Connection) -> sqlite3.Row:
    """Standard accounting test account: name='acct_accounting', strategy='Trend', cash=10_000."""
    create_account(conn, "acct_accounting", "Trend", 10_000.0, "SPY")
    return get_account(conn, "acct_accounting")
