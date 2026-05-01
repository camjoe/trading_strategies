from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from fastapi.testclient import TestClient

from paper_trading_ui.backend.config import TEST_ACCOUNT_NAME, TEST_BACKTEST_ACCOUNT_NAME

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

    def test_post_trade_happy_path_accepts_canonical_manual_account_name(self, api_client: TestClient) -> None:
        with patch(_TICKER_EXISTS, return_value=True):
            resp = api_client.post(
                f"/api/accounts/{TEST_BACKTEST_ACCOUNT_NAME}/trades",
                json={"ticker": "MSFT", "side": "buy", "qty": 1.0, "price": 1.0, "fee": 0.0},
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_post_trade_managed_account_returns_403(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_trade_managed")

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
            json={"ticker": "AAPL", "side": "buy"},
        )
        assert resp.status_code == 422

    def test_post_trade_insufficient_cash_returns_400(self, api_client: TestClient) -> None:
        with patch(_TICKER_EXISTS, return_value=True):
            resp = api_client.post(
                f"/api/accounts/{TEST_ACCOUNT_NAME}/trades",
                json={"ticker": "AAPL", "side": "buy", "qty": 1000.0, "price": 500.0},
            )
        assert resp.status_code == 400
