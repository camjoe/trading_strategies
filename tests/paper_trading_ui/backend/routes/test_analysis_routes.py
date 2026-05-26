"""Tests for the /api/accounts/{account_name}/analysis route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import paper_trading_ui.backend.routes.analysis as analysis_module


def test_returns_analysis_payload_for_valid_account(
    api_client: TestClient,
    seed_account,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_account("acct_analysis")
    expected = {"cash": 1_000.0, "equity": 1_000.0, "positions": []}
    monkeypatch.setattr(
        analysis_module,
        "fetch_account_analysis",
        lambda _conn, *, account_row: expected,
    )

    response = api_client.get("/api/accounts/acct_analysis/analysis")

    assert response.status_code == 200
    assert response.json() == expected


def test_returns_404_for_missing_account(api_client: TestClient) -> None:
    response = api_client.get("/api/accounts/no_such_account/analysis")

    assert response.status_code == 404
