"""Tests for the /api/accounts/{account_name}/analysis route."""

from __future__ import annotations

import paper_trading_web.backend.routes.analysis as analysis_module
import pytest
from fastapi.testclient import TestClient


def test_returns_analysis_payload_for_valid_account(
    api_client: TestClient,
    seed_account,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_account("acct_analysis")
    # fetch_account_analysis returns a snake_case domain payload; the route shapes
    # it into the frontend's camelCase.
    source = {
        "account_return_pct": 1.0,
        "benchmark_return_pct": 0.5,
        "benchmark_ticker": "SPY",
        "alpha_pct": 0.5,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "equity": 1_000.0,
        "top_winners": [],
        "top_losers": [],
        "improvement_notes": [],
    }
    monkeypatch.setattr(
        analysis_module,
        "fetch_account_analysis",
        lambda _conn, *, account_row, provider=None: source,
    )

    response = api_client.get("/api/accounts/acct_analysis/analysis")

    assert response.status_code == 200
    assert response.json() == {
        "accountReturnPct": 1.0,
        "benchmarkReturnPct": 0.5,
        "benchmarkTicker": "SPY",
        "alphaPct": 0.5,
        "realizedPnl": 0.0,
        "unrealizedPnl": 0.0,
        "equity": 1_000.0,
        "topWinners": [],
        "topLosers": [],
        "improvementNotes": [],
    }


def test_returns_404_for_missing_account(api_client: TestClient) -> None:
    response = api_client.get("/api/accounts/no_such_account/analysis")

    assert response.status_code == 404
