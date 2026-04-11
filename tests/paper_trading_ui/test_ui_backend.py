from __future__ import annotations

from fastapi.testclient import TestClient

from trading.database import db
from common.time import utc_now_iso
from trading.services.accounts_service import create_account
from trading.models import AccountConfig


def _create_test_account(
    conn,
    name: str,
    strategy: str = "trend_v1",
    initial_cash: float = 5000.0,
    benchmark: str = "SPY",
    **kwargs,
) -> None:
    create_account(conn, name, strategy, initial_cash, benchmark, config=AccountConfig(**kwargs) if kwargs else None)


def test_backtest_preflight_returns_financial_warnings(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        _create_test_account(
            conn,
            "acct_api_leaps",
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
            "tickersFile": "trading/config/trade_universe.txt",
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
        _create_test_account(conn, "acct_api_conflict")
    finally:
        conn.close()

    response = api_client.post(
        "/api/backtests/preflight",
        json={
            "account": "acct_api_conflict",
            "tickersFile": "trading/config/trade_universe.txt",
            "start": "2026-01-01",
            "lookbackMonths": 1,
        },
    )

    assert response.status_code == 400
    assert "Use either --start or --lookback-months" in response.json()["detail"]


def test_account_detail_exposes_latest_backtest_summary(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        _create_test_account(conn, "acct_api_latest", initial_cash=10000.0)
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
                "trading/config/trade_universe.txt",
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
        _create_test_account(conn, "acct_api_empty", initial_cash=10000.0)
    finally:
        conn.close()

    response = api_client.get("/api/backtests/latest/acct_api_empty")
    assert response.status_code == 200

    payload = response.json()
    assert payload["accountName"] == "acct_api_empty"
    assert payload["latestRun"] is None


def test_admin_create_account_endpoint(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/admin/accounts/create",
        json={
            "name": "acct_admin_create",
            "strategy": "trend",
            "initialCash": 7500,
            "benchmarkTicker": "SPY",
            "descriptiveName": "Admin Created",
            "riskPolicy": "stop_and_target",
            "stopLossPct": 4,
            "takeProfitPct": 8,
            "instrumentMode": "equity",
            "rotationEnabled": True,
            "rotationMode": "time",
            "rotationIntervalDays": 14,
            "rotationIntervalMinutes": 240,
            "rotationSchedule": ["trend", "mean_reversion"],
            "rotationActiveIndex": 0,
            "rotationActiveStrategy": "trend",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["account"]["name"] == "acct_admin_create"
    assert payload["account"]["rotationEnabled"] is True
    assert payload["account"]["rotationMode"] == "time"
    assert payload["account"]["rotationIntervalDays"] == 14
    assert payload["account"]["rotationIntervalMinutes"] == 240
    assert payload["account"]["rotationSchedule"] == ["trend", "mean_reversion"]


def test_admin_delete_account_endpoint(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        _create_test_account(conn, "acct_admin_delete", strategy="trend")
    finally:
        conn.close()

    response = api_client.post(
        "/api/admin/accounts/delete",
        json={"accountName": "acct_admin_delete", "confirm": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["deleted"]["accounts"] == 1


def test_accounts_compare_endpoint(api_client: TestClient) -> None:
    conn = db.ensure_db()
    try:
        _create_test_account(conn, "acct_cmp_a", strategy="trend")
        _create_test_account(conn, "acct_cmp_b", strategy="mean_reversion")
    finally:
        conn.close()

    response = api_client.get("/api/accounts/compare")
    assert response.status_code == 200

    payload = response.json()
    names = {item["name"] for item in payload["accounts"]}
    assert "acct_cmp_a" in names
    assert "acct_cmp_b" in names
