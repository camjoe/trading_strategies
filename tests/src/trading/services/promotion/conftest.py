from __future__ import annotations

import sqlite3

import pytest

from trading.repositories.strategies import StrategyRepository
from trading.services.accounts import create_account


@pytest.fixture
def promotion_account(conn: sqlite3.Connection) -> None:
    """Insert the canonical promotion test account into the test database.

    Tests that exercise promotion actions require an account row to exist.
    This fixture inserts ``acct_service`` with strategy ``trend_v1`` and
    commits, matching the inline setup previously repeated in each test.
    """
    create_account(conn, "acct_service", "trend_v1", 1_000.0, "SPY")
    if StrategyRepository(conn).fetch_by_key(strategy_key="trend") is None:
        StrategyRepository(conn).insert(
            strategy_key="trend",
            primitive="trend",
            params_json="{}",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
