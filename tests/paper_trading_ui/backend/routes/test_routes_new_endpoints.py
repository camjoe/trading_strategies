"""Tests for new endpoints added in the UI-enhancements phase:
  PATCH /api/accounts/{name}/params
  POST  /api/accounts/{name}/trades
  GET   /api/features/status
  POST  /api/features/signals
"""
from __future__ import annotations

from fastapi.testclient import TestClient

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


class TestManualTradeEndpoint:
    def test_post_trade_happy_path(self, api_client: TestClient) -> None:
        _seed_account("acct_trade_happy")

        resp = api_client.post(
            "/api/accounts/acct_trade_happy/trades",
            json={"ticker": "AAPL", "side": "buy", "qty": 10.0, "price": 150.0, "fee": 1.0},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Trade should appear in account detail
        detail = api_client.get("/api/accounts/acct_trade_happy").json()
        tickers = [t["ticker"] for t in detail["trades"]]
        assert "AAPL" in tickers

    def test_post_trade_invalid_side_returns_422(self, api_client: TestClient) -> None:
        _seed_account("acct_trade_422")

        resp = api_client.post(
            "/api/accounts/acct_trade_422/trades",
            json={"ticker": "AAPL", "side": "hold", "qty": 10.0, "price": 150.0},
        )
        assert resp.status_code == 422

    def test_post_trade_missing_required_field_returns_422(self, api_client: TestClient) -> None:
        _seed_account("acct_trade_missing")

        resp = api_client.post(
            "/api/accounts/acct_trade_missing/trades",
            json={"ticker": "AAPL", "side": "buy"},  # missing qty and price
        )
        assert resp.status_code == 422

    def test_post_trade_unknown_account_returns_404(self, api_client: TestClient) -> None:
        resp = api_client.post(
            "/api/accounts/no_such_account/trades",
            json={"ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0},
        )
        assert resp.status_code == 404


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
