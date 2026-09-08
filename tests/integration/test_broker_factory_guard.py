"""Integration test: a persisted account row routes through the broker factory.

Covers the core capability "broker abstraction" from ``docs/overview.md``: the
factory is the sole place broker routing and the ``live_trading_enabled`` guard
live. The exhaustive branch matrix (every transport/venue, the paper-account
assertion, case-insensitivity) is unit-tested in
``tests/src/infrastructure/brokers/test_factory.py`` with hand-built records.

This test covers the seam that suite does not: the ``broker_type`` and
``live_trading_enabled`` columns round-trip from the database through
``get_account`` into the ``AccountRecord`` the factory reads — so the guard
fires on real persisted state, not just a constructed record.
"""

from __future__ import annotations

import sqlite3

import pytest

from common.time import utc_now_iso
from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from trading.services.accounts.mutations import create_account, get_account


def _set_broker_type(conn: sqlite3.Connection, name: str, broker_type: str) -> None:
    conn.execute(
        "UPDATE accounts SET broker_type = ?, updated_at = ? WHERE name = ?",
        (broker_type, utc_now_iso(), name),
    )
    conn.commit()


def test_persisted_paper_account_resolves_to_the_simulator(conn: sqlite3.Connection) -> None:
    create_account(conn, "acct_paper", "trend", 10_000.0, "SPY")
    account = get_account(conn, "acct_paper")

    assert isinstance(get_broker_for_account(account), PaperBrokerAdapter)


def test_persisted_live_web_account_is_refused_without_the_guard(conn: sqlite3.Connection) -> None:
    create_account(conn, "acct_live", "trend", 10_000.0, "SPY")
    # live_trading_enabled defaults to 0; only the transport changes.
    _set_broker_type(conn, "acct_live", "interactive_brokers_web")
    account = get_account(conn, "acct_live")
    assert account.live_trading_enabled == 0

    with pytest.raises(LiveTradingNotEnabledError):
        get_broker_for_account(account)


def test_persisted_unknown_broker_type_fails_loudly(conn: sqlite3.Connection) -> None:
    create_account(conn, "acct_bogus", "trend", 10_000.0, "SPY")
    _set_broker_type(conn, "acct_bogus", "totally_made_up")
    account = get_account(conn, "acct_bogus")

    with pytest.raises(UnknownBrokerTypeError):
        get_broker_for_account(account)
