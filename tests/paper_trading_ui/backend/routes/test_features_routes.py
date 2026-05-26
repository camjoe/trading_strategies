from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

_FEATURE_STATUS = "paper_trading_ui.backend.routes.features.get_provider_status"
_FEATURE_SIGNALS = "paper_trading_ui.backend.routes.features.get_signals"


class TestFeaturesStatusEndpoint:
    def test_status_returns_three_providers(self, api_client: TestClient) -> None:
        with patch(
            _FEATURE_STATUS,
            return_value=[
                {"name": "Policy", "available": True, "fetched_at": "2026-04-24T00:00:00Z", "key_scores": {}},
                {"name": "News", "available": False, "fetched_at": "2026-04-24T00:00:00Z", "key_scores": {}},
                {"name": "Social", "available": True, "fetched_at": "2026-04-24T00:00:00Z", "key_scores": {}},
            ],
        ) as mocked:
            resp = api_client.get("/api/features/status")
        mocked.assert_called_once_with()
        assert resp.status_code == 200

        body = resp.json()
        assert "providers" in body
        assert len(body["providers"]) == 3

    def test_status_provider_entries_have_required_fields(self, api_client: TestClient) -> None:
        with patch(
            _FEATURE_STATUS,
            return_value=[
                {"name": "Policy", "available": True, "fetched_at": "2026-04-24T00:00:00Z", "key_scores": {"x": 1}},
                {"name": "News", "available": False, "fetched_at": "2026-04-24T00:00:00Z", "key_scores": {}},
                {"name": "Social", "available": True, "fetched_at": "2026-04-24T00:00:00Z", "key_scores": {"y": 2}},
            ],
        ) as mocked:
            resp = api_client.get("/api/features/status")
        mocked.assert_called_once_with()
        providers = resp.json()["providers"]

        for provider in providers:
            assert "name" in provider
            assert "available" in provider
            assert "fetched_at" in provider
            assert "key_scores" in provider
            assert isinstance(provider["available"], bool)
            assert isinstance(provider["key_scores"], dict)


class TestFeaturesSignalsEndpoint:
    def test_signals_returns_three_strategies(self, api_client: TestClient) -> None:
        with patch(
            _FEATURE_SIGNALS,
            return_value=[
                {"strategy": "policy_regime", "signal": "buy", "available": False},
                {"strategy": "news_sentiment", "signal": "hold", "available": False},
                {"strategy": "social_trend_rotation", "signal": "sell", "available": False},
            ],
        ) as mocked:
            resp = api_client.post("/api/features/signals", json={"ticker": "spy"})
        mocked.assert_called_once_with("SPY")
        assert resp.status_code == 200

        body = resp.json()
        assert body["ticker"] == "SPY"
        assert len(body["signals"]) == 3

    def test_signals_entries_have_required_fields(self, api_client: TestClient) -> None:
        with patch(
            _FEATURE_SIGNALS,
            return_value=[
                {"strategy": "policy_regime", "signal": "buy", "available": False},
                {"strategy": "news_sentiment", "signal": "hold", "available": False},
                {"strategy": "social_trend_rotation", "signal": "sell", "available": False},
            ],
        ) as mocked:
            resp = api_client.post("/api/features/signals", json={"ticker": "AAPL"})
        mocked.assert_called_once_with("AAPL")
        signals = resp.json()["signals"]

        for signal in signals:
            assert "strategy" in signal
            assert "signal" in signal
            assert "available" in signal
            assert signal["signal"] in ("buy", "sell", "hold")

    def test_signals_missing_ticker_returns_422(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/features/signals", json={})
        assert resp.status_code == 422

    def test_signals_empty_ticker_returns_422(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/features/signals", json={"ticker": ""})
        assert resp.status_code == 422
