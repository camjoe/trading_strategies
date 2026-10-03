import json
import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest

import infrastructure.brokers.ibkr_web.client as ib_web_client_module
import infrastructure.brokers.ibkr_web.settings as ib_web_settings_module
from infrastructure.brokers.ibkr_web.client import (
    IbWebOrderStatusUnavailableError,
    InteractiveBrokersWebClient,
    _is_marketdata_preflight_only,
    _is_order_reply_message,
    _truthy_flag,
)
from infrastructure.brokers.ibkr_web.pacing import IbWebApiPacingLimiter
from infrastructure.brokers.ibkr_web.settings import IbWebApiSettings, load_ib_web_api_settings


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

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ({"account_id": "U1234567", "verify_ssl": "maybe"}, "Invalid boolean value"),
            ({"account_id": "U1234567", "timeout_seconds": "0"}, "timeout_seconds"),
            ({"account_id": "U1234567", "keepalive_enabled": "maybe"}, "Invalid boolean value"),
            ({"account_id": "U1234567", "keepalive_interval_seconds": "0"}, "keepalive_interval_seconds"),
        ],
    )
    def test_invalid_payload_values_raise_value_error(self, monkeypatch, payload, message):
        monkeypatch.setattr(ib_web_settings_module, "_file_payload", lambda _path: payload)

        with pytest.raises(ValueError, match=message):
            load_ib_web_api_settings()

    def test_verify_ssl_and_keepalive_enabled_reject_none_from_bool_coercion(self, monkeypatch):
        monkeypatch.setattr(ib_web_settings_module, "_file_payload", lambda _path: {"account_id": "U1234567"})
        monkeypatch.setenv("TRADING_IBKR_WEB_API_VERIFY_SSL", "forced-none")
        monkeypatch.setenv("TRADING_IBKR_WEB_API_KEEPALIVE_ENABLED", "forced-none")
        original_coerce_bool = ib_web_settings_module.coerce_bool
        monkeypatch.setattr(
            ib_web_settings_module,
            "coerce_bool",
            lambda value: None if value == "forced-none" else original_coerce_bool(value),
        )

        with pytest.raises(ValueError, match="verify_ssl"):
            load_ib_web_api_settings()

        monkeypatch.delenv("TRADING_IBKR_WEB_API_VERIFY_SSL")
        with pytest.raises(ValueError, match="keepalive_enabled"):
            load_ib_web_api_settings()


def _make_settings(**overrides) -> IbWebApiSettings:
    return IbWebApiSettings(
        base_url="https://example.test",
        account_id="U1234567",
        headers={},
        **overrides,
    )


class TestLoadIbWebApiSettingsHelpers:
    def test_file_payload_rejects_non_object_json(self):
        class _FakePath:
            def exists(self) -> bool:
                return True

            def read_text(self, encoding: str) -> str:
                assert encoding == "utf-8"
                return "[]"

            def __str__(self) -> str:
                return "fake-config.json"

        with pytest.raises(ValueError, match="JSON object"):
            ib_web_settings_module._file_payload(_FakePath())

    @pytest.mark.parametrize("value", ['["x"]', '"token"'])
    def test_coerce_headers_rejects_string_payloads_that_do_not_decode_to_dict(self, value):
        with pytest.raises(ValueError, match="JSON object"):
            ib_web_settings_module._coerce_headers(value)

    def test_coerce_headers_rejects_non_mapping_values(self):
        with pytest.raises(ValueError, match="mapping"):
            ib_web_settings_module._coerce_headers([("Authorization", "secret")])


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

        response = client.submit_order(
            {"conid": 265598, "side": "BUY", "orderType": "MKT", "tif": "DAY", "quantity": 1}
        )

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

    def test_account_id_property_returns_configured_account(self):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())

        assert client.account_id == "U1234567"

    @pytest.mark.parametrize(
        ("status", "message"),
        [
            ({"authenticated": False, "connected": True}, "not authenticated"),
            ({"authenticated": True, "connected": False}, "not connected"),
        ],
    )
    def test_validate_session_rejects_invalid_auth_state(self, monkeypatch, status, message):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "fetch_auth_status", lambda: status)

        with pytest.raises(RuntimeError, match=message):
            client.validate_session()

    def test_validate_session_rejects_missing_portfolio_account(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "fetch_auth_status", lambda: {"authenticated": True, "connected": True})
        monkeypatch.setattr(client, "fetch_portfolio_account_ids", lambda: ["U0000001"])

        with pytest.raises(RuntimeError, match="not visible"):
            client.validate_session()

    def test_validate_session_rejects_account_not_trade_enabled(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "fetch_auth_status", lambda: {"authenticated": True, "connected": True})
        monkeypatch.setattr(client, "fetch_portfolio_account_ids", lambda: ["U1234567"])
        monkeypatch.setattr(client, "fetch_trade_account_ids", lambda: ["U0000001"])

        with pytest.raises(RuntimeError, match="not enabled for trading"):
            client.validate_session()

    def test_disconnect_closes_owned_http_client(self):
        fake_http_client = MagicMock()
        with patch.object(ib_web_client_module.httpx, "Client", return_value=fake_http_client):
            client = InteractiveBrokersWebClient(settings=_make_settings())

        client.disconnect()

        fake_http_client.close.assert_called_once_with()

    @pytest.mark.parametrize(
        ("method_name", "payload", "message"),
        [
            ("fetch_auth_status", [], "auth status"),
            ("fetch_trade_accounts", [], "trading accounts"),
            ("tickle", [], "tickle response"),
            ("fetch_ledger", [], "ledger response"),
            ("fetch_summary", [], "summary response"),
            ("fetch_order_status", [], "order status response"),
        ],
    )
    def test_object_endpoints_reject_non_object_payloads(self, monkeypatch, method_name, payload, message):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: payload)

        with pytest.raises(RuntimeError, match=message):
            getattr(client, method_name)(*("42",) if method_name == "fetch_order_status" else ())

    def test_fetch_portfolio_account_ids_rejects_non_list_payload(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: {"accountId": "U1"})

        with pytest.raises(RuntimeError, match="must be a list"):
            client.fetch_portfolio_account_ids()

    def test_fetch_portfolio_account_ids_ignores_non_dict_items_and_uses_fallback_keys(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(
            client,
            "_request_json",
            lambda *args, **kwargs: [
                "skip",
                {},
                {"desc": "U1000001"},
                {"displayName": "U1000002"},
                {"id": "U1000003"},
            ],
        )

        assert client.fetch_portfolio_account_ids() == ["U1000001", "U1000002", "U1000003"]

    def test_fetch_trade_account_ids_supports_list_and_falls_back_to_empty(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        responses = iter([["U1", "", "U2"], {"accounts": "not-a-list"}])
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

        assert client.fetch_trade_account_ids() == ["U1", "U2"]
        assert client.fetch_trade_account_ids() == []

    @pytest.mark.parametrize(
        "method_name",
        ["fetch_trade_accounts", "fetch_ledger", "fetch_summary"],
    )
    def test_object_endpoints_return_dict_payloads(self, monkeypatch, method_name):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: {"ok": True})

        assert getattr(client, method_name)() == {"ok": True}

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ("not-a-collection", "positions response"),
            ({"positions": "bad"}, "positions response"),
            ({"unexpected": []}, "positions response"),
            (["bad"], "orders list"),
            ({"orders": "bad"}, "orders list"),
            ({"not_orders": []}, "orders list"),
            ({"trades": []}, "trades response"),
        ],
    )
    def test_collection_endpoints_reject_invalid_shapes(self, monkeypatch, payload, message):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: payload)

        if "positions" in message:
            method = client.fetch_positions
        elif "orders" in message:
            method = client.fetch_orders
        else:
            method = client.fetch_trades
        with pytest.raises(RuntimeError, match=message):
            method()

    def test_fetch_positions_accepts_list_and_object_positions_list(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        responses = iter(
            [
                [{"ticker": "AAPL"}, "skip"],
                {"positions": [{"ticker": "MSFT"}, "skip"]},
            ]
        )
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

        assert client.fetch_positions() == [{"ticker": "AAPL"}]
        assert client.fetch_positions() == [{"ticker": "MSFT"}]

    def test_fetch_orders_returns_filtered_order_rows(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: {"orders": [{"orderId": 1}, "skip"]})

        assert client.fetch_orders() == [{"orderId": 1}]

    def test_resolve_conid_returns_contract_conid(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(
            client,
            "resolve_contract",
            lambda symbol: ib_web_client_module.IbWebApiContract(
                conid="265598",
                ticker=symbol,
                sec_type="STK",
                listing_exchange="NASDAQ",
            ),
        )

        assert client.resolve_conid("AAPL") == "265598"

    def test_resolve_contract_requires_symbol(self):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())

        with pytest.raises(ValueError, match="Ticker symbol is required"):
            client.resolve_contract("   ")

    def test_resolve_contract_uses_cache(self):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        cached = ib_web_client_module.IbWebApiContract(
            conid="265598",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client._contract_cache["AAPL"] = cached

        assert client.resolve_contract(" aapl ") is cached

    def test_resolve_contract_rejects_non_list_search_payload(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: {"conid": "1"})

        with pytest.raises(RuntimeError, match="must be a list"):
            client.resolve_contract("AAPL")

    def test_resolve_contract_returns_matching_symbol_details(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(
            client,
            "_request_json",
            lambda *args, **kwargs: [{"conid": "11", "symbol": "MSFT"}, {"conid": "22", "ticker": "AAPL"}],
        )
        monkeypatch.setattr(client, "_load_contract_details", lambda symbol, conid: {"symbol": symbol, "conid": conid})

        assert client.resolve_contract("AAPL") == {"symbol": "AAPL", "conid": "22"}

    def test_resolve_contract_uses_fallback_conid_when_symbol_never_matches(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(
            client,
            "_request_json",
            lambda *args, **kwargs: [{"conid": "11", "symbol": "MSFT"}, {"conid": "22", "ticker": "QQQ"}],
        )
        monkeypatch.setattr(client, "_load_contract_details", lambda symbol, conid: {"symbol": symbol, "conid": conid})

        assert client.resolve_contract("AAPL") == {"symbol": "AAPL", "conid": "11"}

    def test_resolve_contract_raises_when_no_conid_is_found(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: [{"symbol": "AAPL"}, "skip"])

        with pytest.raises(RuntimeError, match="could not resolve"):
            client.resolve_contract("AAPL")

    def test_fetch_marketdata_snapshot_rejects_invalid_response_shapes(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: {"conid": "1"})

        with pytest.raises(RuntimeError, match="must be a list"):
            client.fetch_marketdata_snapshot(["1"])

        responses = iter([[{"conid": "1"}], {"conid": "1"}])
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

        with pytest.raises(RuntimeError, match="follow-up response must be a list"):
            client.fetch_marketdata_snapshot(["1"])

    def test_fetch_marketdata_snapshot_returns_first_rows_when_not_preflight_only(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: [{"conid": "1", "31": "123.45"}, "skip"])

        assert client.fetch_marketdata_snapshot(["1"]) == [{"conid": "1", "31": "123.45"}]

    def test_submit_order_rejects_confirmation_loops_and_error_payloads(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        monkeypatch.setattr(
            client, "_request_json", lambda *args, **kwargs: [{"id": "reply-1", "message": ["confirm"]}]
        )

        with pytest.raises(RuntimeError, match="safety limit"):
            client.submit_order({"ticker": "AAPL"})

        responses = iter([{"error": "order rejected"}, {"unexpected": True}])
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

        with pytest.raises(RuntimeError, match="order rejected"):
            client.submit_order({"ticker": "AAPL"})
        with pytest.raises(RuntimeError, match="did not return an acknowledgement"):
            client.submit_order({"ticker": "AAPL"})

    def test_load_contract_details_validates_shapes_and_caches_defaults(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        responses = iter(
            [
                [],
                {"secdef": "bad"},
                {"secdef": ["skip", {"conid": "other"}, {"conid": "77"}]},
                {"secdef": [{"conid": "88"}]},
            ]
        )
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

        with pytest.raises(RuntimeError, match="must be an object"):
            client._load_contract_details("AAPL", "77")
        with pytest.raises(RuntimeError, match="secdef list"):
            client._load_contract_details("AAPL", "77")

        contract = client._load_contract_details("AAPL", "77")
        assert contract == ib_web_client_module.IbWebApiContract(
            conid="77",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="SMART",
        )
        assert client._conid_cache["AAPL"] == "77"
        assert client._contract_cache["AAPL"] == contract

        with pytest.raises(RuntimeError, match="could not load security details"):
            client._load_contract_details("AAPL", "99")

    def test_cancel_order_returns_payload_and_rejects_non_object_payload(self, monkeypatch):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        responses = iter([{"cancelled": True}, []])
        monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

        assert client.cancel_order("42") == {"cancelled": True}
        with pytest.raises(RuntimeError, match="cancel-order response"):
            client.cancel_order("42")

    def test_request_json_wraps_non_429_http_errors(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom", request=request)

        client = InteractiveBrokersWebClient(
            settings=_make_settings(),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        with pytest.raises(RuntimeError, match="request failed"):
            client._request_json("GET", "/iserver/auth/status")

    def test_fetch_order_status_classifies_documented_cache_miss(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="order status unavailable", request=request)

        client = InteractiveBrokersWebClient(
            settings=_make_settings(),
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://example.test",
            ),
        )

        with pytest.raises(IbWebOrderStatusUnavailableError, match="503"):
            client.fetch_order_status("42")

    def test_fetch_order_status_preserves_other_transport_failures(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized", request=request)

        client = InteractiveBrokersWebClient(
            settings=_make_settings(),
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://example.test",
            ),
        )

        with pytest.raises(RuntimeError, match="401"):
            client.fetch_order_status("42")

    def test_request_json_returns_empty_dict_for_empty_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"", request=request)

        client = InteractiveBrokersWebClient(
            settings=_make_settings(),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )

        assert client._request_json("GET", "/tickle") == {}

    def test_start_keepalive_is_skipped_when_disabled_or_already_running(self):
        disabled_client = InteractiveBrokersWebClient(
            settings=_make_settings(keepalive_enabled=False),
            http_client=MagicMock(),
        )
        disabled_client._start_keepalive_if_enabled()
        assert disabled_client._keepalive_thread is None

        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())

        class _AliveThread:
            started = False

            def is_alive(self) -> bool:
                return True

            def start(self) -> None:
                self.started = True

        alive_thread = _AliveThread()
        client._keepalive_thread = alive_thread
        client._start_keepalive_if_enabled()

        assert client._keepalive_thread is alive_thread
        assert alive_thread.started is False

    def test_run_keepalive_loop_stops_when_disconnected_or_tickle_fails(self, monkeypatch):
        client = InteractiveBrokersWebClient(
            settings=_make_settings(keepalive_interval_seconds=0.01), http_client=MagicMock()
        )

        class _WaitOnce:
            def __init__(self) -> None:
                self.calls = 0

            def wait(self, _interval: float) -> bool:
                self.calls += 1
                return False

        disconnected_event = _WaitOnce()
        client._keepalive_stop_event = disconnected_event
        client._connected = False
        client._run_keepalive_loop()
        assert disconnected_event.calls == 1

        failing_event = _WaitOnce()
        client._keepalive_stop_event = failing_event
        client._connected = True
        monkeypatch.setattr(client, "tickle", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        client._run_keepalive_loop()

        assert failing_event.calls == 1
        assert client.is_connected() is False
        assert isinstance(client._background_error, RuntimeError)
        assert "keepalive failed" in str(client._background_error)

    def test_raise_if_background_error_propagates(self):
        client = InteractiveBrokersWebClient(settings=_make_settings(), http_client=MagicMock())
        client._background_error = RuntimeError("background boom")

        with pytest.raises(RuntimeError, match="background boom"):
            client._raise_if_background_error()


class TestIbWebClientHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, True), ("yes", True), ("off", False), (None, False)],
    )
    def test_truthy_flag(self, value, expected):
        assert _truthy_flag(value) is expected

    def test_is_marketdata_preflight_only_handles_empty_and_real_fields(self):
        assert _is_marketdata_preflight_only([]) is False
        assert _is_marketdata_preflight_only([{"conid": "1"}]) is True
        assert _is_marketdata_preflight_only([{"conid": "1", "31": "100.0"}]) is False

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [(None, False), ([], False), ([{"id": "1"}, {"id": "2"}], True), ([{"id": "1"}, {"message": []}], False)],
    )
    def test_is_order_reply_message(self, payload, expected):
        assert _is_order_reply_message(payload) is expected
