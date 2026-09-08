"""Integration test for the cross-account portfolio risk rollup.

Covers the core capability "cross-account portfolio risk rollup" from
``docs/overview.md``: exposure and symbol concentration aggregate across every
account. The test seeds two accounts, each with an equity snapshot and an open
position, then reads both rollups and confirms they combine the accounts.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from tests.support.books import ensure_default_book_id
from tests.support.evaluation import insert_account_snapshot
from trading.repositories.positions import PositionRepository
from trading.services.accounts.mutations import create_account
from trading.services.analysis.concentration import fetch_portfolio_concentration
from trading.services.analysis.exposure import fetch_portfolio_exposure


def _seed_account_with_position(
    conn: sqlite3.Connection, *, name: str, symbol: str, equity: float, market_value: float
) -> None:
    create_account(conn, name, "trend", equity, "SPY")
    account_id = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()[0]
    insert_account_snapshot(
        conn,
        account_id=account_id,
        snapshot_time="2026-05-01T00:00:00Z",
        cash=equity - market_value,
        market_value=market_value,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    PositionRepository(conn).upsert(
        book_id=ensure_default_book_id(conn, account_id),
        symbol=symbol,
        qty=10.0,
        avg_cost=market_value / 10.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        updated_at=utc_now_iso(),
    )


def test_rollups_aggregate_across_accounts(conn: sqlite3.Connection) -> None:
    _seed_account_with_position(conn, name="acct_one", symbol="AAA", equity=10_000.0, market_value=4_000.0)
    _seed_account_with_position(conn, name="acct_two", symbol="BBB", equity=20_000.0, market_value=8_000.0)
    conn.commit()

    exposure = fetch_portfolio_exposure(conn)
    assert exposure.accounts_with_snapshots == 2
    assert exposure.total_equity == 30_000.0
    assert exposure.total_market_value == 12_000.0

    concentration = fetch_portfolio_concentration(conn)
    symbols = {entry.symbol for entry in concentration.symbols}
    assert {"AAA", "BBB"} <= symbols
