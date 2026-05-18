"""Seed module for trade and equity snapshot data used in the shared seeded_conn fixture."""

from __future__ import annotations

import sqlite3

from tests.support.seed_accounts import ACCT_TREND, seed_account_id

# ---------------------------------------------------------------------------
# Public name constants
# ---------------------------------------------------------------------------

TRADE_BUY_AAPL = "AAPL"
TRADE_BUY_MSFT = "MSFT"
TRADE_SELL_AAPL = "AAPL"

SNAPSHOT_T1 = "2026-01-01T00:00:00"
SNAPSHOT_T2 = "2026-01-02T00:00:00"
SNAPSHOT_T3 = "2026-01-03T00:00:00"


def seed_trades(conn: sqlite3.Connection) -> None:
    acct_id = seed_account_id(conn, ACCT_TREND)
    conn.executemany(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (acct_id, TRADE_BUY_AAPL, "buy", 10.0, 150.0, 0.0, "2026-01-02T10:00:00", "entry"),
            (acct_id, TRADE_BUY_MSFT, "buy", 5.0, 300.0, 0.0, "2026-01-03T10:00:00", "entry"),
            (acct_id, TRADE_SELL_AAPL, "sell", 10.0, 160.0, 0.0, "2026-01-10T10:00:00", "exit"),
        ],
    )


def seed_snapshots(conn: sqlite3.Connection) -> None:
    acct_id = seed_account_id(conn, ACCT_TREND)
    conn.executemany(
        """
        INSERT INTO equity_snapshots
            (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (acct_id, SNAPSHOT_T1, 9_500.0, 500.0, 10_000.0, 0.0, 0.0),
            (acct_id, SNAPSHOT_T2, 9_200.0, 800.0, 10_050.0, 0.0, 50.0),
            (acct_id, SNAPSHOT_T3, 9_000.0, 1_100.0, 10_100.0, 100.0, 50.0),
        ],
    )


__all__ = [
    "SNAPSHOT_T1",
    "SNAPSHOT_T2",
    "SNAPSHOT_T3",
    "TRADE_BUY_AAPL",
    "TRADE_BUY_MSFT",
    "TRADE_SELL_AAPL",
    "seed_snapshots",
    "seed_trades",
]
