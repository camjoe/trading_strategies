import json
import threading

import httpx
import pytest

from trading.brokers.ib_web_client import (
    IbWebApiPacingLimiter,
    IbWebApiSettings,
    InteractiveBrokersWebClient,
    load_ib_web_api_settings,
)


class TestLoadIbWebApiSettings:
    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("TRADING_IBKR_WEB_API_ACCOUNT_ID", "U1234567")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_BASE_URL", "https://example.test/v1/api")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_HEADERS_JSON", json.dumps({"Authorization": "Bearer secret"}))
        monkeypatch.setenv("TRADING_IBKR_WEB_API_VERIFY_SSL", "false")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_TIMEOUT_SECONDS", "7.5")

        settings = load_ib_web_api_settings()

        assert settings.account_id == "U1234567"
        assert settings.base_url == "https://example.test/v1/api"
        assert settings.headers["Authorization"] == "Bearer secret"
        assert settings.verify_ssl is False
        assert settings.timeout_seconds == 7.5

    def test_loads_from_file_and_applies_session_cookie(self, tmp_path, monkeypatch):
        config_path = tmp_path / "ibkr_web_api_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "account_id": "U7654321",
                    "base_url": "https://example.test/v1/api",
                    "session_token": "abc123",
                    "verify_ssl": True,
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADING_IBKR_WEB_API_CONFIG", str(config_path))
        monkeypatch.delenv("TRADING_IBKR_WEB_API_ACCOUNT_ID", raising=False)

        settings = load_ib_web_api_settings()

        assert settings.account_id == "U7654321"
        assert settings.headers["Cookie"] == "api=abc123"

    def test_defaults_to_local_gateway_when_base_url_not_provided(self, tmp_path, monkeypatch):
        config_path = tmp_path / "ibkr_web_api_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "account_id": "U7654321",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADING_IBKR_WEB_API_CONFIG", str(config_path))
        monkeypatch.delenv("TRADING_IBKR_WEB_API_ACCOUNT_ID", raising=False)

        settings = load_ib_web_api_settings()

        assert settings.base_url == "https://localhost:5000/v1/api"
        assert settings.verify_ssl is False
        assert settings.keepalive_enabled is True
        assert settings.keepalive_interval_seconds == 60.0

    def test_loads_keepalive_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("TRADING_IBKR_WEB_API_ACCOUNT_ID", "U1234567")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_KEEPALIVE_ENABLED", "false")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_KEEPALIVE_INTERVAL_SECONDS", "90")

        settings = load_ib_web_api_settings()

        assert settings.keepalive_enabled is False
        assert settings.keepalive_interval_seconds == 90.0

    def test_missing_account_id_raises(self, tmp_path, monkeypatch):
        config_path = tmp_path / "ibkr_web_api_config.json"
        config_path.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_CONFIG", str(config_path))
        monkeypatch.delenv("TRADING_IBKR_WEB_API_ACCOUNT_ID", raising=False)

        with pytest.raises(ValueError, match="account_id"):
            load_ib_web_api_settings()


class TestInteractiveBrokersWebClient:
    def test_pacing_limiter_enforces_portfolio_accounts_spacing(self):
        class _Clock:
            def __init__(self) -> None:
                self.now = 100.0
                self.sleeps: list[float] = []

            def monotonic(self) -> float:
                return self.now

            def sleep(self, seconds: float) -> None:
                self.sleeps.append(seconds)
                self.now += seconds

        clock = _Clock()
        limiter = IbWebApiPacingLimiter(time_fn=clock.monotonic, sleep_fn=clock.sleep)

        limiter.wait_for_slot("GET", "/portfolio/accounts")
        limiter.wait_for_slot("GET", "/portfolio/accounts")

        assert clock.sleeps == [5.0]

    def test_pacing_limiter_enforces_global_limit(self):
        class _Clock:
            def __init__(self) -> None:
                self.now = 0.0
                self.sleeps: list[float] = []

            def monotonic(self) -> float:
                return self.now

            def sleep(self, seconds: float) -> None:
                self.sleeps.append(seconds)
                self.now += seconds

        clock = _Clock()
        limiter = IbWebApiPacingLimiter(time_fn=clock.monotonic, sleep_fn=clock.sleep)

        for index in range(11):
            limiter.wait_for_slot("GET", f"/custom/{index}")

        assert clock.sleeps == [1.0]

    def test_validate_session_checks_account_visibility(self):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/iserver/auth/status":
                return httpx.Response(200, json={"authenticated": True, "connected": True})
            if request.url.path == "/portfolio/accounts":
                return httpx.Response(200, json=[{"accountId": "U1234567"}])
            if request.url.path == "/iserver/accounts":
                return httpx.Response(200, json={"accounts": ["U1234567"]})
            raise AssertionError(f"Unexpected path {request.url.path}")

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        try:
            client.connect()

            assert client.is_connected() is True
            assert calls == ["/iserver/auth/status", "/portfolio/accounts", "/iserver/accounts"]
        finally:
            client.disconnect()

    def test_fetch_marketdata_snapshot_retries_after_preflight(self):
        responses = [
            httpx.Response(200, json=[{"conid": 265598, "conidEx": "265598"}]),
            httpx.Response(200, json=[{"conid": 265598, "31": "168.42", "84": "168.41", "86": "168.43"}]),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        rows = client.fetch_marketdata_snapshot(["265598"])

        assert rows[0]["31"] == "168.42"

    def test_submit_order_confirms_reply_message(self):
        responses = [
            httpx.Response(200, json=[{"id": "reply-1", "message": ["Confirm me"]}]),
            httpx.Response(200, json=[{"order_id": "42", "order_status": "Submitted"}]),
        ]
        seen: list[str] = []
        payloads: list[object] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(f"{request.method} {request.url.path}")
            if request.url.path == "/iserver/account/U1234567/orders":
                payloads.append(json.loads(request.content.decode("utf-8")))
            return responses.pop(0)

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        response = client.submit_order({"conid": 265598, "side": "BUY", "orderType": "MKT", "tif": "DAY", "quantity": 1})

        assert response["order_id"] == "42"
        assert seen == [
            "POST /iserver/account/U1234567/orders",
            "POST /iserver/reply/reply-1",
        ]
        assert payloads == [
            {
                "orders": [
                    {
                        "conid": 265598,
                        "side": "BUY",
                        "orderType": "MKT",
                        "tif": "DAY",
                        "quantity": 1,
                    }
                ]
            }
        ]

    def test_fetch_order_status_returns_object(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/iserver/account/order/status/42"
            return httpx.Response(200, json={"order_id": "42", "order_status": "PreSubmitted"})

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        payload = client.fetch_order_status("42")

        assert payload["order_status"] == "PreSubmitted"

    def test_fetch_trades_returns_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/iserver/account/trades"
            assert request.url.params["days"] == "1"
            return httpx.Response(200, json=[{"symbol": "AAPL", "side": "BUY", "size": 1}])

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        rows = client.fetch_trades()

        assert rows == [{"symbol": "AAPL", "side": "BUY", "size": 1}]

    def test_request_json_raises_pacing_specific_error_for_429(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="Too Many Requests", request=request)

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
            pacing_limiter=IbWebApiPacingLimiter(),
        )

        with pytest.raises(RuntimeError, match="pacing limit exceeded"):
            client.fetch_auth_status()

    def test_connect_starts_keepalive_and_tickle_runs(self):
        tickled = threading.Event()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/iserver/auth/status":
                return httpx.Response(200, json={"authenticated": True, "connected": True})
            if request.url.path == "/portfolio/accounts":
                return httpx.Response(200, json=[{"accountId": "U1234567"}])
            if request.url.path == "/iserver/accounts":
                return httpx.Response(200, json={"accounts": ["U1234567"]})
            if request.url.path == "/tickle":
                tickled.set()
                return httpx.Response(200, json={"session": "ok"})
            raise AssertionError(f"Unexpected path {request.url.path}")

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="U1234567",
                headers={},
                keepalive_enabled=True,
                keepalive_interval_seconds=0.01,
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        try:
            client.connect()
            assert tickled.wait(0.5)
        finally:
            client.disconnect()
