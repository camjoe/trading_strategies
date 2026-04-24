from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest
from fastapi import HTTPException

from paper_trading_ui.backend.routes.backtests import (
    api_backtest_preflight,
    api_latest_backtest_for_account,
)
from paper_trading_ui.backend.schemas import BacktestPreflightRequest


def test_backtest_preflight_returns_financial_warnings(
    conn: sqlite3.Connection,
    create_route_test_account: Callable[..., None],
) -> None:
    create_route_test_account(
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


def test_backtest_preflight_rejects_start_and_lookback_conflict(
    conn: sqlite3.Connection,
    create_route_test_account: Callable[..., None],
) -> None:
    create_route_test_account(conn, "acct_api_conflict")

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


def test_latest_backtest_endpoint_returns_none_when_missing(
    conn: sqlite3.Connection,
    create_route_test_account: Callable[..., None],
) -> None:
    create_route_test_account(conn, "acct_api_empty", initial_cash=10000.0)

    payload = api_latest_backtest_for_account("acct_api_empty")

    assert payload["accountName"] == "acct_api_empty"
    assert payload["latestRun"] is None
