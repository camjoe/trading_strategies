from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from common.time import utc_now_iso
from paper_trading_ui.backend.routes.accounts import api_account_detail, api_accounts_compare
from paper_trading_ui.backend.routes.admin import api_admin_create_account, api_admin_delete_account
from paper_trading_ui.backend.routes.backtests import (
    api_backtest_preflight,
    api_latest_backtest_for_account,
)
from paper_trading_ui.backend.schemas import (
    AdminCreateAccountRequest,
    AdminDeleteAccountRequest,
    BacktestPreflightRequest,
)
from trading.database.db_migrations import DEFAULT_ROTATION_OVERLAY_WATCHLIST
from trading.models import AccountConfig
from trading.services.accounts import create_account


def _create_test_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str = "trend_v1",
    initial_cash: float = 5000.0,
    benchmark: str = "SPY",
    **kwargs: object,
) -> None:
    create_account(conn, name, strategy, initial_cash, benchmark, config=AccountConfig(**kwargs) if kwargs else None)


def test_backtest_preflight_returns_financial_warnings(conn: sqlite3.Connection) -> None:
    _create_test_account(
        conn,
        "acct_api_leaps",
        instrument_mode="leaps",
        option_strike_offset_pct=5.0,
        option_min_dte=120,
        option_max_dte=365,
        option_type="call",
    )

    payload = api_backtest_preflight(
        BacktestPreflightRequest(
            account="acct_api_leaps",
            tickersFile="trading/config/trade_universe.txt",
            start="2026-01-01",
            end="2026-03-01",
            allowApproximateLeaps=False,
        )
    )

    assert any("LEAPs mode is approximated" in warning for warning in payload["warnings"])
    assert any("opt-in was not enabled" in warning for warning in payload["warnings"])


def test_backtest_preflight_rejects_start_and_lookback_conflict(conn: sqlite3.Connection) -> None:
    _create_test_account(conn, "acct_api_conflict")

    with pytest.raises(HTTPException) as exc_info:
        api_backtest_preflight(
            BacktestPreflightRequest(
                account="acct_api_conflict",
                tickersFile="trading/config/trade_universe.txt",
                start="2026-01-01",
                lookbackMonths=1,
            )
        )

    assert exc_info.value.status_code == 400
    assert "Use either --start or --lookback-months" in str(exc_info.value.detail)


def test_account_detail_exposes_latest_backtest_summary(conn: sqlite3.Connection) -> None:
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

    payload = api_account_detail("acct_api_latest")

    assert payload["account"]["accountKind"] == "managed"
    assert payload["account"]["brokerType"] == "paper"
    latest = payload["latestBacktest"]
    assert latest is not None
    assert latest["accountName"] == "acct_api_latest"
    assert latest["runName"] == "latest-run"


def test_latest_backtest_endpoint_returns_none_when_missing(conn: sqlite3.Connection) -> None:
    _create_test_account(conn, "acct_api_empty", initial_cash=10000.0)

    payload = api_latest_backtest_for_account("acct_api_empty")

    assert payload["accountName"] == "acct_api_empty"
    assert payload["latestRun"] is None


def test_admin_create_account_endpoint(conn: sqlite3.Connection) -> None:
    del conn

    payload = api_admin_create_account(
        AdminCreateAccountRequest(
            name="acct_admin_create",
            strategy="trend",
            initialCash=7500,
            benchmarkTicker="SPY",
            descriptiveName="Admin Created",
            riskPolicy="stop_and_target",
            stopLossPct=4,
            takeProfitPct=8,
            tradeSizePct=12,
            maxPositionPct=24,
            instrumentMode="equity",
            rotationEnabled=True,
            rotationMode="regime",
            rotationIntervalDays=14,
            rotationIntervalMinutes=240,
            rotationSchedule=["trend", "ma_crossover", "mean_reversion"],
            rotationRegimeStrategyRiskOn="trend",
            rotationRegimeStrategyNeutral="ma_crossover",
            rotationRegimeStrategyRiskOff="mean_reversion",
            rotationOverlayMode="news",
            rotationOverlayMinTickers=2,
            rotationOverlayConfidenceThreshold=0.5,
            rotationOverlayWatchlist=["AAPL", "MSFT", "NVDA"],
            rotationActiveIndex=0,
            rotationActiveStrategy="trend",
        )
    )

    assert payload["status"] == "ok"
    assert payload["account"]["name"] == "acct_admin_create"
    assert payload["account"]["tradeSizePct"] == 12
    assert payload["account"]["maxPositionPct"] == 24
    assert payload["account"]["rotationEnabled"] is True
    assert payload["account"]["rotationMode"] == "regime"
    assert payload["account"]["rotationIntervalDays"] == 14
    assert payload["account"]["rotationIntervalMinutes"] == 240
    assert payload["account"]["rotationSchedule"] == ["trend", "ma_crossover", "mean_reversion"]
    assert payload["account"]["rotationRegimeStrategyRiskOn"] == "trend"
    assert payload["account"]["rotationRegimeStrategyNeutral"] == "ma_crossover"
    assert payload["account"]["rotationRegimeStrategyRiskOff"] == "mean_reversion"
    assert payload["account"]["rotationOverlayMode"] == "news"
    assert payload["account"]["rotationOverlayMinTickers"] == 2
    assert payload["account"]["rotationOverlayConfidenceThreshold"] == 0.5
    assert payload["account"]["rotationOverlayWatchlist"] == ["AAPL", "MSFT", "NVDA"]


def test_admin_create_account_uses_seeded_watchlist_when_omitted(conn: sqlite3.Connection) -> None:
    del conn

    payload = api_admin_create_account(
        AdminCreateAccountRequest(
            name="acct_admin_seeded_watchlist",
            strategy="trend",
            initialCash=5000,
            benchmarkTicker="SPY",
            rotationEnabled=True,
            rotationMode="regime",
            rotationIntervalMinutes=240,
            rotationSchedule=["trend", "ma_crossover", "mean_reversion"],
            rotationRegimeStrategyRiskOn="trend",
            rotationRegimeStrategyNeutral="ma_crossover",
            rotationRegimeStrategyRiskOff="mean_reversion",
            rotationOverlayMode="news_social",
            rotationOverlayMinTickers=2,
            rotationOverlayConfidenceThreshold=0.5,
            rotationActiveIndex=0,
            rotationActiveStrategy="trend",
        )
    )

    assert payload["status"] == "ok"
    assert payload["account"]["name"] == "acct_admin_seeded_watchlist"
    assert payload["account"]["rotationOverlayWatchlist"] == DEFAULT_ROTATION_OVERLAY_WATCHLIST


def test_admin_delete_account_endpoint(conn: sqlite3.Connection) -> None:
    _create_test_account(conn, "acct_admin_delete", strategy="trend")

    payload = api_admin_delete_account(
        AdminDeleteAccountRequest(accountName="acct_admin_delete", confirm=True)
    )

    assert payload["status"] == "ok"
    assert payload["deleted"]["accounts"] == 1


def test_accounts_compare_endpoint(conn: sqlite3.Connection) -> None:
    _create_test_account(conn, "acct_cmp_a", strategy="trend")
    _create_test_account(conn, "acct_cmp_b", strategy="mean_reversion")

    payload = api_accounts_compare()

    names = {item["name"] for item in payload["accounts"]}
    assert "acct_cmp_a" in names
    assert "acct_cmp_b" in names
