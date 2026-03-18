from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trading import db
from trading.accounts import create_account, utc_now_iso
from trading.db_backend import SQLiteBackend, get_backend, set_backend


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading_ui.db"))
    from paper_trading_ui.backend.main import app
    try:
        with TestClient(app) as client:
            yield client
    finally:
        set_backend(original)


def test_backtest_preflight_returns_financial_warnings(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        create_account(
            conn,
            "acct_api_leaps",
            "trend_v1",
            5000.0,
            "SPY",
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )
    finally:
        conn.close()

    response = api_client.post(
        "/api/backtests/preflight",
        json={
            "account": "acct_api_leaps",
            "tickersFile": "trading/trade_universe.txt",
            "start": "2026-01-01",
            "end": "2026-03-01",
            "allowApproximateLeaps": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert any("LEAPs mode is approximated" in warning for warning in payload["warnings"])
    assert any("opt-in was not enabled" in warning for warning in payload["warnings"])


def test_backtest_preflight_rejects_start_and_lookback_conflict(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        create_account(conn, "acct_api_conflict", "trend_v1", 5000.0, "SPY")
    finally:
        conn.close()

    response = api_client.post(
        "/api/backtests/preflight",
        json={
            "account": "acct_api_conflict",
            "tickersFile": "trading/trade_universe.txt",
            "start": "2026-01-01",
            "lookbackMonths": 1,
        },
    )

    assert response.status_code == 400
    assert "Use either --start or --lookback-months" in response.json()["detail"]


def test_account_detail_exposes_latest_backtest_summary(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        create_account(conn, "acct_api_latest", "trend_v1", 10000.0, "SPY")
        acct = conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_api_latest",)).fetchone()
        assert acct is not None

        conn.execute(
            """
            INSERT INTO backtest_runs (
                account_id,
                run_name,
                start_date,
                end_date,
                created_at,
                slippage_bps,
                fee_per_trade,
                tickers_file,
                notes,
                warnings
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(acct["id"]),
                "latest-run",
                "2026-01-01",
                "2026-01-31",
                utc_now_iso(),
                5.0,
                0.0,
                "trading/trade_universe.txt",
                "seed test run",
                "daily bars only",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    response = api_client.get("/api/accounts/acct_api_latest")
    assert response.status_code == 200

    payload = response.json()
    latest = payload["latestBacktest"]
    assert latest is not None
    assert latest["accountName"] == "acct_api_latest"
    assert latest["runName"] == "latest-run"


def test_latest_backtest_endpoint_returns_none_when_missing(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        create_account(conn, "acct_api_empty", "trend_v1", 10000.0, "SPY")
    finally:
        conn.close()

    response = api_client.get("/api/backtests/latest/acct_api_empty")
    assert response.status_code == 200

    payload = response.json()
    assert payload["accountName"] == "acct_api_empty"
    assert payload["latestRun"] is None
