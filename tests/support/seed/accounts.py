"""Seed module for account-level test data used in the shared seeded_conn fixture."""

from __future__ import annotations

import sqlite3

from trading.models import AccountConfig
from trading.services.accounts import create_account

# ---------------------------------------------------------------------------
# Public name constants
# ---------------------------------------------------------------------------

ACCT_TREND = "seed_trend"
ACCT_MOMENTUM = "seed_momentum"
ACCT_LOCAL = "seed_local"

# Strategy used across promotion and backtest seed data
PROMOTION_STRATEGY = "trend_v1"


def seed_account_id(conn: sqlite3.Connection, name: str) -> int:
    """Return the id of a named seed account; raises if missing."""
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    assert row is not None, f"seed account '{name}' not found"
    return int(row["id"])


def seed_accounts(conn: sqlite3.Connection) -> None:
    create_account(conn, ACCT_TREND, "trend_v1", 10_000.0, "SPY")
    create_account(conn, ACCT_MOMENTUM, "momentum_v1", 8_000.0, "QQQ")
    create_account(
        conn,
        ACCT_LOCAL,
        "trend_v1",
        5_000.0,
        "SPY",
        config=AccountConfig(account_kind="local"),
    )


def seed_global_settings(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO global_settings (id) VALUES (1)")


__all__ = [
    "ACCT_LOCAL",
    "ACCT_MOMENTUM",
    "ACCT_TREND",
    "PROMOTION_STRATEGY",
    "seed_account_id",
    "seed_accounts",
    "seed_global_settings",
]
