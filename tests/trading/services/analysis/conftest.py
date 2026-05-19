from __future__ import annotations

import sqlite3

import pytest

from tests.trading.services.analysis.helpers import make_analysis_account


@pytest.fixture
def analysis_account(conn: sqlite3.Connection) -> sqlite3.Row:
    """Standard analysis account seeded with 1 000 initial cash.

    Use this instead of calling ``make_analysis_account`` directly in tests
    that only need the default setup.
    """
    return make_analysis_account(conn, "acct", initial_cash=1_000.0)
