from __future__ import annotations

import sqlite3
from collections.abc import Callable

from paper_trading_ui.backend.routes.admin import api_admin_create_account, api_admin_delete_account
from paper_trading_ui.backend.schemas import (
    AdminCreateAccountRequest,
    AdminDeleteAccountRequest,
)
from trading.database.db_migrations import DEFAULT_ROTATION_OVERLAY_WATCHLIST


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


def test_admin_delete_account_endpoint(
    conn: sqlite3.Connection,
    create_route_test_account: Callable[..., None],
) -> None:
    create_route_test_account(conn, "acct_admin_delete", strategy="trend")

    payload = api_admin_delete_account(
        AdminDeleteAccountRequest(accountName="acct_admin_delete", confirm=True),
    )

    assert payload["status"] == "ok"
    assert payload["deleted"]["accounts"] == 1
