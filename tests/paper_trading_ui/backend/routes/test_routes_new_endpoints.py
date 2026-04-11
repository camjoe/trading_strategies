"""Tests for new endpoints added in the UI-enhancements phase:
  PATCH /api/accounts/{name}/params
  POST  /api/accounts/{name}/trades
  GET   /api/features/status
  POST  /api/features/signals
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from paper_trading_ui.backend.config import TEST_ACCOUNT_NAME
from trading.database import db
from trading.services.accounts_service import create_account
from trading.models import AccountConfig


def _seed_account(name: str, strategy: str = "trend_v1", risk_policy: str = "none") -> None:
    conn = db.ensure_db()
    try:
        create_account(
            conn,
            name,
            strategy,
            5000.0,
            "SPY",
            config=AccountConfig(risk_policy=risk_policy) if risk_policy != "none" else None,
        )
    finally:
        conn.close()


class TestAccountParamsEndpoint:
    def test_patch_params_updates_strategy(self, api_client: TestClient) -> None:
        _seed_account("acct_params_strategy")

        resp = api_client.patch(
            "/api/accounts/acct_params_strategy/params",
            json={"strategy": "mean_reversion"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Confirm the change persisted
        detail = api_client.get("/api/accounts/acct_params_strategy").json()
        assert detail["account"]["strategy"] == "mean_reversion"

    def test_patch_params_updates_risk_policy(self, api_client: TestClient) -> None:
        _seed_account("acct_params_risk")

        resp = api_client.patch(
            "/api/accounts/acct_params_risk/params",
            json={"riskPolicy": "fixed_stop"},
        )
        assert resp.status_code == 200

        detail = api_client.get("/api/accounts/acct_params_risk").json()
        assert detail["account"]["riskPolicy"] == "fixed_stop"

    def test_patch_params_empty_body_is_no_op(self, api_client: TestClient) -> None:
        _seed_account("acct_params_noop")

        resp = api_client.patch("/api/accounts/acct_params_noop/params", json={})
        assert resp.status_code == 200

    def test_patch_params_unknown_account_returns_404(self, api_client: TestClient) -> None:
        resp = api_client.patch(
            "/api/accounts/no_such_account/params",
            json={"strategy": "trend"},
        )
        assert resp.status_code == 404

    def test_patch_params_invalid_risk_policy_returns_422(self, api_client: TestClient) -> None:
        _seed_account("acct_params_invalid_risk")

        resp = api_client.patch(
            "/api/accounts/acct_params_invalid_risk/params",
            json={"riskPolicy": "not_a_real_policy"},
        )
        assert resp.status_code == 422

    def test_patch_params_invalid_goal_range_returns_422(self, api_client: TestClient) -> None:
        _seed_account("acct_params_invalid_goal")

        # goal_min > goal_max should be rejected by configure_account
        resp = api_client.patch(
            "/api/accounts/acct_params_invalid_goal/params",
            json={"goalMinReturnPct": 0.50, "goalMaxReturnPct": 0.10},
        )
        assert resp.status_code == 422

    def test_patch_params_updates_rotation_fields(self, api_client: TestClient) -> None:
        _seed_account("acct_params_rotation")

        resp = api_client.patch(
            "/api/accounts/acct_params_rotation/params",
            json={
                "rotationEnabled": True,
                "rotationMode": "regime",
                "rotationOptimalityMode": "average_return",
                "rotationIntervalDays": 7,
                "rotationIntervalMinutes": 240,
                "rotationLookbackDays": 30,
                "rotationSchedule": ["trend", "ma_crossover", "mean_reversion"],
                "rotationRegimeStrategyRiskOn": "trend",
                "rotationRegimeStrategyNeutral": "ma_crossover",
                "rotationRegimeStrategyRiskOff": "mean_reversion",
                "rotationOverlayMode": "news_social",
                "rotationOverlayMinTickers": 2,
                "rotationOverlayConfidenceThreshold": 0.55,
                "rotationActiveIndex": 1,
                "rotationActiveStrategy": "ma_crossover",
                "rotationLastAt": "2026-03-20T00:00:00Z",
            },
        )
        assert resp.status_code == 200

        detail = api_client.get("/api/accounts/acct_params_rotation").json()
        account = detail["account"]
        assert account["rotationEnabled"] is True
        assert account["rotationMode"] == "regime"
        assert account["rotationOptimalityMode"] == "average_return"
        assert account["rotationIntervalDays"] == 7
        assert account["rotationIntervalMinutes"] == 240
        assert account["rotationLookbackDays"] == 30
        assert account["rotationSchedule"] == ["trend", "ma_crossover", "mean_reversion"]
        assert account["rotationRegimeStrategyRiskOn"] == "trend"
        assert account["rotationRegimeStrategyNeutral"] == "ma_crossover"
        assert account["rotationRegimeStrategyRiskOff"] == "mean_reversion"
        assert account["rotationOverlayMode"] == "news_social"
        assert account["rotationOverlayMinTickers"] == 2
        assert account["rotationOverlayConfidenceThreshold"] == pytest.approx(0.55)
        assert account["rotationActiveIndex"] == 1
        assert account["rotationActiveStrategy"] == "ma_crossover"
        assert account["rotationLastAt"] == "2026-03-20T00:00:00Z"


_TICKER_EXISTS = "paper_trading_ui.backend.routes.trades._ticker_exists"


class TestManualTradeEndpoint:
    def test_post_trade_happy_path(self, api_client: TestClient) -> None:
        with patch(_TICKER_EXISTS, return_value=True):
            resp = api_client.post(
                f"/api/accounts/{TEST_ACCOUNT_NAME}/trades",
                json={"ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 1.0, "fee": 0.0},
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        detail = api_client.get(f"/api/accounts/{TEST_ACCOUNT_NAME}").json()
        tickers = [t["ticker"] for t in detail["trades"]]
        assert "AAPL" in tickers

    def test_post_trade_managed_account_returns_403(self, api_client: TestClient) -> None:
        _seed_account("acct_trade_managed")

        resp = api_client.post(
            "/api/accounts/acct_trade_managed/trades",
            json={"ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0},
        )
        assert resp.status_code == 403

    def test_post_trade_unknown_ticker_returns_400(self, api_client: TestClient) -> None:
        with patch(_TICKER_EXISTS, return_value=False):
            resp = api_client.post(
                f"/api/accounts/{TEST_ACCOUNT_NAME}/trades",
                json={"ticker": "ASDFA", "side": "buy", "qty": 1.0, "price": 10.0},
            )
        assert resp.status_code == 400
        assert "ASDFA" in resp.json()["detail"]

    def test_post_trade_invalid_side_returns_422(self, api_client: TestClient) -> None:
        resp = api_client.post(
            f"/api/accounts/{TEST_ACCOUNT_NAME}/trades",
            json={"ticker": "AAPL", "side": "hold", "qty": 10.0, "price": 150.0},
        )
        assert resp.status_code == 422

    def test_post_trade_missing_required_field_returns_422(self, api_client: TestClient) -> None:
        resp = api_client.post(
            f"/api/accounts/{TEST_ACCOUNT_NAME}/trades",
            json={"ticker": "AAPL", "side": "buy"},  # missing qty and price
        )
        assert resp.status_code == 422

    def test_post_trade_insufficient_cash_returns_400(self, api_client: TestClient) -> None:
        # test_account_bt is auto-created with $1 initial cash; a large buy must fail.
        with patch(_TICKER_EXISTS, return_value=True):
            resp = api_client.post(
                f"/api/accounts/{TEST_ACCOUNT_NAME}/trades",
                json={"ticker": "AAPL", "side": "buy", "qty": 1000.0, "price": 500.0},
            )
        assert resp.status_code == 400


class TestFeaturesStatusEndpoint:
    def test_status_returns_three_providers(self, api_client: TestClient) -> None:
        resp = api_client.get("/api/features/status")
        assert resp.status_code == 200

        body = resp.json()
        assert "providers" in body
        assert len(body["providers"]) == 3

    def test_status_provider_entries_have_required_fields(self, api_client: TestClient) -> None:
        resp = api_client.get("/api/features/status")
        providers = resp.json()["providers"]

        for p in providers:
            assert "name" in p
            assert "available" in p
            assert "fetched_at" in p
            assert "key_scores" in p
            assert isinstance(p["available"], bool)
            assert isinstance(p["key_scores"], dict)


class TestFeaturesSignalsEndpoint:
    def test_signals_returns_three_strategies(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/features/signals", json={"ticker": "SPY"})
        assert resp.status_code == 200

        body = resp.json()
        assert body["ticker"] == "SPY"
        assert len(body["signals"]) == 3

    def test_signals_entries_have_required_fields(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/features/signals", json={"ticker": "AAPL"})
        signals = resp.json()["signals"]

        for s in signals:
            assert "strategy" in s
            assert "signal" in s
            assert "available" in s
            assert s["signal"] in ("buy", "sell", "hold")

    def test_signals_missing_ticker_returns_422(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/features/signals", json={})
        assert resp.status_code == 422

    def test_signals_empty_ticker_returns_422(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/features/signals", json={"ticker": ""})
        assert resp.status_code == 422
