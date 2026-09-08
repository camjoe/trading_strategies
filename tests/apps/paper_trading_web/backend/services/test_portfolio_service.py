"""Tests for the backend portfolio rollup payload shaping."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from paper_trading_web.backend.services.portfolio import build_portfolio_rollup_payload

from tests.support.books import ensure_default_book_id
from trading.repositories.positions import PositionRepository
from trading.repositories.snapshots import EquitySnapshotRepository


def test_empty_db_shapes_empty_payload(conn: sqlite3.Connection) -> None:
    payload = build_portfolio_rollup_payload(conn)

    assert payload["exposure"] == {
        "accounts": [],
        "accountCount": 0,
        "accountsWithSnapshots": 0,
        "totalCash": 0.0,
        "totalMarketValue": 0.0,
        "totalEquity": 0.0,
    }
    assert payload["concentration"] == {"symbols": [], "sectors": [], "totalMarketValue": 0.0}


def test_shapes_camel_case_exposure_and_concentration(
    conn: sqlite3.Connection,
    create_account_row: Callable[..., int],
) -> None:
    account_id = create_account_row("alpha")
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, account_id),
        snapshot_time="2026-07-09T00:00:00Z",
        cash=800.0,
        market_value=200.0,
        equity=1_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    PositionRepository(conn).upsert(
        book_id=ensure_default_book_id(conn, account_id),
        symbol="AAPL",
        qty=1.0,
        avg_cost=200.0,
        market_value=200.0,
        unrealized_pnl=0.0,
        updated_at="2026-07-09T00:00:00Z",
    )

    payload = build_portfolio_rollup_payload(conn)

    (account_entry,) = payload["exposure"]["accounts"]
    assert account_entry == {
        "accountId": account_id,
        "accountName": "alpha",
        "snapshotTime": "2026-07-09T00:00:00Z",
        "cash": 800.0,
        "marketValue": 200.0,
        "equity": 1_000.0,
        "positionCount": 1,
    }
    (symbol_entry,) = payload["concentration"]["symbols"]
    assert symbol_entry["symbol"] == "AAPL"
    assert symbol_entry["portfolioPct"] == 100.0
    assert symbol_entry["accountNames"] == ["alpha"]
