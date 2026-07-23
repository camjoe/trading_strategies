"""
Shared session-level test database seed module.

``seed_session_db(conn)`` populates a freshly initialised database with a
canonical, named dataset that covers the most common test scenarios across
the repository and service test suites.

Usage convention
----------------
Tests that only *read* or *filter* data should accept the ``seeded_conn``
fixture (session-scoped) instead of the per-test ``conn`` fixture.  Tests
that write, delete, or depend on an empty-table state must continue using
the function-scoped ``conn`` fixture so they get an isolated database.

The seed data is **read-only by convention**.  Nothing enforces this at the
SQLite level, so mutating the seeded connection from a test will silently
corrupt the shared state for all subsequent tests in that worker.

Named constants
---------------
Import these constants in test modules to reference seeded entities without
hard-coding string literals:

    from tests.support.seed.db import ACCT_TREND, ACCT_MOMENTUM, ACCT_LOCAL

All constants are also importable directly from their domain module, e.g.::

    from tests.support.seed.accounts import ACCT_TREND
    from tests.support.seed.reporting import SNAPSHOT_T1
    from tests.support.seed.book_data import BOOK_TREND
"""

from __future__ import annotations

import sqlite3

from tests.support.seed.accounts import (
    ACCT_LOCAL,
    ACCT_MOMENTUM,
    ACCT_TREND,
    PROMOTION_STRATEGY,
    seed_accounts,
    seed_global_settings,
)
from tests.support.seed.backtesting import BACKTEST_RUN_NAME, seed_backtest_run
from tests.support.seed.book_data import (
    BOOK_METRIC_DATE,
    BOOK_STRATEGY,
    BOOK_TREND,
    seed_books,
)
from tests.support.seed.promotion_review import seed_promotion_review
from tests.support.seed.reporting import (
    SNAPSHOT_T1,
    SNAPSHOT_T2,
    SNAPSHOT_T3,
    TRADE_BUY_AAPL,
    TRADE_BUY_MSFT,
    TRADE_SELL_AAPL,
    seed_snapshots,
    seed_trades,
)


def seed_session_db(conn: sqlite3.Connection) -> None:
    """Populate *conn* with the canonical session-level dataset.

    Call this exactly once per session (the ``seeded_conn`` fixture does
    this automatically).  Do not call it from individual tests.
    """
    seed_accounts(conn)
    seed_global_settings(conn)
    seed_trades(conn)
    seed_snapshots(conn)
    seed_backtest_run(conn)
    seed_promotion_review(conn)
    seed_books(conn)
    conn.commit()


__all__ = [
    "ACCT_LOCAL",
    "ACCT_MOMENTUM",
    "ACCT_TREND",
    "BACKTEST_RUN_NAME",
    "PROMOTION_STRATEGY",
    "BOOK_METRIC_DATE",
    "BOOK_STRATEGY",
    "BOOK_TREND",
    "SNAPSHOT_T1",
    "SNAPSHOT_T2",
    "SNAPSHOT_T3",
    "TRADE_BUY_AAPL",
    "TRADE_BUY_MSFT",
    "TRADE_SELL_AAPL",
    "seed_session_db",
]
