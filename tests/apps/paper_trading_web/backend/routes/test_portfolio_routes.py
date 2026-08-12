"""Tests for the /api/portfolio/rollup route."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from tests.support.books import ensure_default_book_id
from trading.repositories.positions import PositionRepository
from trading.repositories.snapshots import EquitySnapshotRepository


def _account_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return int(row["id"])


def test_returns_empty_rollup_without_accounts(api_client: TestClient) -> None:
    response = api_client.get("/api/portfolio/rollup")

    assert response.status_code == 200
    payload = response.json()
    assert payload["exposure"]["accounts"] == []
    assert payload["exposure"]["totalEquity"] == 0.0
    assert payload["concentration"]["symbols"] == []
    assert payload["concentration"]["totalMarketValue"] == 0.0


def test_returns_exposure_and_concentration_payload(
    api_client: TestClient,
    api_conn: sqlite3.Connection,
    seed_account,
) -> None:
    seed_account("alpha")
    seed_account("beta")
    alpha_id = _account_id(api_conn, "alpha")
    EquitySnapshotRepository(api_conn).insert_for_book(
        book_id=ensure_default_book_id(api_conn, alpha_id),
        snapshot_time="2026-07-09T00:00:00Z",
        cash=4_000.0,
        market_value=1_000.0,
        equity=5_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    PositionRepository(api_conn).upsert(
        book_id=ensure_default_book_id(api_conn, alpha_id),
        symbol="AAPL",
        qty=5.0,
        avg_cost=180.0,
        market_value=1_000.0,
        unrealized_pnl=100.0,
        updated_at="2026-07-09T00:00:00Z",
    )

    response = api_client.get("/api/portfolio/rollup")

    assert response.status_code == 200
    payload = response.json()

    exposure = payload["exposure"]
    assert exposure["accountCount"] == 2
    assert exposure["accountsWithSnapshots"] == 1
    assert exposure["totalEquity"] == 5_000.0
    by_name = {entry["accountName"]: entry for entry in exposure["accounts"]}
    assert by_name["alpha"]["snapshotTime"] == "2026-07-09T00:00:00Z"
    assert by_name["alpha"]["positionCount"] == 1
    assert by_name["beta"]["snapshotTime"] is None
    assert by_name["beta"]["equity"] is None

    concentration = payload["concentration"]
    assert concentration["totalMarketValue"] == 1_000.0
    (symbol_entry,) = concentration["symbols"]
    assert symbol_entry["symbol"] == "AAPL"
    assert symbol_entry["portfolioPct"] == 100.0
    assert symbol_entry["accountCount"] == 1
    assert symbol_entry["accountNames"] == ["alpha"]
    assert concentration["sectors"][0]["portfolioPct"] == 100.0
