from __future__ import annotations

import sqlite3

import pytest

from trading.services.accounts.mutations import create_account, get_account


@pytest.fixture
def eval_account(conn: sqlite3.Connection) -> sqlite3.Row:
    """Standard evaluation account: name='acct_eval', strategy='trend_v1', cash=1000."""
    create_account(conn, "acct_eval", "trend_v1", 1_000.0, "SPY")
    return get_account(conn, "acct_eval")
