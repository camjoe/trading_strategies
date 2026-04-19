"""Tests for the broker abstraction layer.

Covers:
  - PaperBrokerAdapter — immediate fill behaviour
  - InteractiveBrokersAdapter — IBClientProtocol interactions (mocked)
  - get_broker_for_account factory routing and live_trading_enabled guard
  - _map_ib_status status mapping
  - reconcile_open_ib_orders fill-reconciliation loop
  - Live trading safety: live_trading_enabled = 1 must never be set in tests
"""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from trading.models.broker_order import BrokerOrder, OrderFill, OrderStatus, OrderType, TimeInForce
from trading.brokers.factory import LiveTradingNotEnabledError, get_broker_for_account
from trading.brokers.ib_adapter import InteractiveBrokersAdapter, _map_ib_status
from trading.brokers.ib_client import IBClientProtocol, IbApiClient
from trading.brokers.ib_web_adapter import InteractiveBrokersWebAdapter
from trading.brokers.ib_web_client import (
    IbWebApiPacingLimiter,
    IbWebApiSettings,
    InteractiveBrokersWebClient,
    load_ib_web_api_settings,
)
from trading.brokers.paper_adapter import PaperBrokerAdapter
from trading.database.db import init_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_account(**kwargs):
    """Return a dict-like account row. live_trading_enabled defaults to 0."""
    defaults = {
        "id": 1,
        "name": "test-account",
        "broker_type": "paper",
        "broker_host": None,
        "broker_port": None,
        "broker_client_id": None,
        # SAFETY: must always be 0 in tests. Never override to 1.
        "live_trading_enabled": 0,
    }
    defaults.update(kwargs)
    return defaults


def _make_order(**kwargs) -> BrokerOrder:
    defaults = dict(account_id=1, ticker="AAPL", side="buy", qty=10.0, price=150.0)
    defaults.update(kwargs)
    return BrokerOrder(**defaults)


def _mock_ib_client() -> MagicMock:
    """Return a MagicMock that satisfies IBClientProtocol (including factory methods)."""
    client = MagicMock()
    client.is_connected.return_value = True
    return client


def _adapter_with_mock_client() -> tuple[InteractiveBrokersAdapter, MagicMock]:
    client = _mock_ib_client()
    adapter = InteractiveBrokersAdapter(client=client, host="127.0.0.1", port=7497, client_id=1)
    return adapter, client


# ---------------------------------------------------------------------------
# PaperBrokerAdapter
# ---------------------------------------------------------------------------


class TestPaperBrokerAdapter:
    def test_place_order_fills_immediately(self):
        adapter = PaperBrokerAdapter()
        order = _make_order()
        filled = adapter.place_order(order)

        assert filled.status == OrderStatus.FILLED
        assert filled.filled_qty == order.qty
        assert filled.avg_fill_price == order.price
        assert filled.commission == 0.0
        assert filled.broker_order_id is not None
        assert filled.broker_order_id.startswith("paper-")
        assert len(filled.fills) == 1

    def test_fill_records_correct_fill_details(self):
        adapter = PaperBrokerAdapter()
        order = _make_order(qty=5.0, price=200.0)
        filled = adapter.place_order(order)

        fill: OrderFill = filled.fills[0]
        assert fill.filled_qty == 5.0
        assert fill.fill_price == 200.0
        assert fill.commission == 0.0
        assert fill.fill_time is not None

    def test_place_order_sets_submitted_and_updated_at(self):
        adapter = PaperBrokerAdapter()
        filled = adapter.place_order(_make_order())
        assert filled.submitted_at is not None
        assert filled.updated_at is not None

    def test_connect_and_disconnect_are_noops(self):
        adapter = PaperBrokerAdapter()
        adapter.connect()
        adapter.disconnect()

    def test_cancel_order_raises(self):
        with pytest.raises(NotImplementedError):
            PaperBrokerAdapter().cancel_order("paper-abc")

    def test_get_open_trades_returns_empty_list(self):
        assert PaperBrokerAdapter().get_open_trades() == []

    def test_get_positions_raises(self):
        with pytest.raises(NotImplementedError):
            PaperBrokerAdapter().get_positions()

    def test_get_account_info_raises(self):
        with pytest.raises(NotImplementedError):
            PaperBrokerAdapter().get_account_info()

    def test_get_quotes_raises(self):
        with pytest.raises(NotImplementedError):
            PaperBrokerAdapter().get_quotes(["AAPL"])


# ---------------------------------------------------------------------------
# Factory routing
# ---------------------------------------------------------------------------


class TestGetBrokerForAccount:
    def test_paper_account_returns_paper_adapter(self):
        broker = get_broker_for_account(_make_account(broker_type="paper"))
        assert isinstance(broker, PaperBrokerAdapter)

    def test_missing_broker_type_defaults_to_paper(self):
        broker = get_broker_for_account(_make_account(broker_type=None))
        assert isinstance(broker, PaperBrokerAdapter)

    def test_ib_without_live_trading_enabled_raises(self):
        account = _make_account(broker_type="interactive_brokers", live_trading_enabled=0)
        with pytest.raises(LiveTradingNotEnabledError, match="live_trading_enabled"):
            get_broker_for_account(account)

    def test_ib_error_message_mentions_manual_requirement(self):
        account = _make_account(broker_type="interactive_brokers", live_trading_enabled=0)
        with pytest.raises(LiveTradingNotEnabledError, match="manually"):
            get_broker_for_account(account)

    def test_ib_with_live_trading_enabled_connects(self):
        account = _make_account(
            broker_type="interactive_brokers",
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        with (
            patch("trading.brokers.factory._require_live_trading_enabled"),
            patch("trading.brokers.factory.IbAsyncClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersAdapter)
        mock_client.connect.assert_called_once_with("127.0.0.1", 7497, client_id=1)

    def test_live_trading_enabled_missing_key_treated_as_disabled(self):
        account = {"id": 1, "name": "old-account", "broker_type": "interactive_brokers"}
        with pytest.raises(LiveTradingNotEnabledError):
            get_broker_for_account(account)

    def test_live_trading_enabled_string_one_is_accepted(self):
        """String "1" (from SQLite row) is accepted — guard should not raise."""
        account = _make_account(
            broker_type="interactive_brokers",
            live_trading_enabled="1",
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        with patch("trading.brokers.factory.IbAsyncClient", return_value=mock_client):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersAdapter)

    def test_ibapi_backend_uses_ib_api_client(self):
        import trading.brokers.factory as factory_module

        account = _make_account(
            broker_type="interactive_brokers",
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        original = factory_module.IB_CLIENT_BACKEND
        try:
            factory_module.IB_CLIENT_BACKEND = "ibapi"
            with (
                patch("trading.brokers.factory._require_live_trading_enabled"),
                patch("trading.brokers.factory.IbApiClient", return_value=mock_client),
            ):
                broker = get_broker_for_account(account)
            assert isinstance(broker, InteractiveBrokersAdapter)
        finally:
            factory_module.IB_CLIENT_BACKEND = original

    def test_unknown_ib_backend_raises_value_error(self):
        import trading.brokers.factory as factory_module

        account = _make_account(broker_type="interactive_brokers")
        original = factory_module.IB_CLIENT_BACKEND
        try:
            factory_module.IB_CLIENT_BACKEND = "not_a_real_backend"
            with patch("trading.brokers.factory._require_live_trading_enabled"):
                with pytest.raises(ValueError, match="Unknown IB_CLIENT_BACKEND"):
                    get_broker_for_account(account)
        finally:
            factory_module.IB_CLIENT_BACKEND = original

    def test_ib_web_without_live_trading_enabled_raises(self):
        account = _make_account(broker_type="interactive_brokers_web", live_trading_enabled=0)
        with pytest.raises(LiveTradingNotEnabledError, match="live_trading_enabled"):
            get_broker_for_account(account)

    def test_ib_web_with_live_trading_enabled_connects(self):
        account = _make_account(broker_type="interactive_brokers_web")
        mock_client = MagicMock()
        with (
            patch("trading.brokers.factory._require_live_trading_enabled"),
            patch(
                "trading.brokers.factory.load_ib_web_api_settings",
                return_value=IbWebApiSettings(
                    base_url="https://example.test/v1/api",
                    account_id="U1234567",
                    headers={},
                ),
            ),
            patch("trading.brokers.factory.InteractiveBrokersWebClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersWebAdapter)
        mock_client.connect.assert_called_once_with()


# ---------------------------------------------------------------------------
# InteractiveBrokersAdapter (mocked IBClientProtocol)
# ---------------------------------------------------------------------------


class TestInteractiveBrokersAdapter:
    # connect / disconnect

    def test_connect_delegates_to_client(self):
        adapter, client = _adapter_with_mock_client()
        adapter.connect()
        client.connect.assert_called_once_with("127.0.0.1", 7497, client_id=1)

    def test_disconnect_calls_client_disconnect_when_connected(self):
        adapter, client = _adapter_with_mock_client()
        adapter.disconnect()
        client.disconnect.assert_called_once()

    def test_disconnect_skips_when_not_connected(self):
        adapter, client = _adapter_with_mock_client()
        client.is_connected.return_value = False
        adapter.disconnect()
        client.disconnect.assert_not_called()

    def test_require_connected_raises_when_disconnected(self):
        adapter, client = _adapter_with_mock_client()
        client.is_connected.return_value = False
        with pytest.raises(RuntimeError, match="not connected"):
            adapter._require_connected()

    # place_order

    def test_place_order_returns_submitted_status(self):
        adapter, client = _adapter_with_mock_client()
        mock_trade = MagicMock()
        mock_trade.order.orderId = 42
        client.place_order.return_value = mock_trade

        result = adapter.place_order(_make_order())

        assert result.status == OrderStatus.SUBMITTED
        assert result.broker_order_id == "42"
        assert result.submitted_at is not None

    def test_place_order_market_sends_mkt_type(self):
        adapter, client = _adapter_with_mock_client()
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1
        client.place_order.return_value = mock_trade

        adapter.place_order(_make_order(order_type=OrderType.MARKET))

        call_kwargs = client.make_order.call_args.kwargs
        assert call_kwargs["orderType"] == "MKT"

    def test_place_order_limit_sends_lmt_type_and_price(self):
        adapter, client = _adapter_with_mock_client()
        mock_trade = MagicMock()
        mock_trade.order.orderId = 2
        client.place_order.return_value = mock_trade

        adapter.place_order(_make_order(order_type=OrderType.LIMIT, price=148.0))

        call_kwargs = client.make_order.call_args.kwargs
        assert call_kwargs["orderType"] == "LMT"
        assert call_kwargs["lmtPrice"] == 148.0

    # cancel_order

    def test_cancel_order_calls_client_cancel(self):
        adapter, client = _adapter_with_mock_client()
        mock_trade = MagicMock()
        mock_trade.order.orderId = 99
        client.trades.return_value = [mock_trade]

        adapter.cancel_order("99")
        client.cancel_order.assert_called_once_with(mock_trade.order)

    def test_cancel_order_raises_when_not_found(self):
        adapter, client = _adapter_with_mock_client()
        client.trades.return_value = []
        with pytest.raises(ValueError, match="No open IB order"):
            adapter.cancel_order("999")

    # get_positions

    def test_get_positions_returns_symbol_qty_dict(self):
        adapter, client = _adapter_with_mock_client()
        pos1 = SimpleNamespace(contract=SimpleNamespace(symbol="AAPL"), position=10.0)
        pos2 = SimpleNamespace(contract=SimpleNamespace(symbol="MSFT"), position=5.0)
        client.positions.return_value = [pos1, pos2]

        assert adapter.get_positions() == {"AAPL": 10.0, "MSFT": 5.0}

    # get_account_info

    def test_get_account_info_filters_to_known_usd_tags(self):
        adapter, client = _adapter_with_mock_client()
        summary = [
            SimpleNamespace(tag="TotalCashValue", value="50000.0", currency="USD"),
            SimpleNamespace(tag="BuyingPower", value="100000.0", currency="USD"),
            SimpleNamespace(tag="SomeOtherTag", value="999.0", currency="USD"),
            SimpleNamespace(tag="TotalCashValue", value="45000.0", currency="EUR"),
        ]
        client.account_summary.return_value = summary

        result = adapter.get_account_info()
        assert result["TotalCashValue"] == 50000.0
        assert result["BuyingPower"] == 100000.0
        assert "SomeOtherTag" not in result

    # get_quotes

    def test_get_quotes_returns_bid_ask_last(self):
        adapter, client = _adapter_with_mock_client()
        mock_ticker = SimpleNamespace(
            contract=SimpleNamespace(symbol="AAPL"),
            bid=149.0, ask=150.0, last=149.5,
        )
        client.req_tickers.return_value = [mock_ticker]
        client.qualify_contracts.return_value = None

        result = adapter.get_quotes(["AAPL"])
        assert result == {"AAPL": {"bid": 149.0, "ask": 150.0, "last": 149.5}}

    # get_open_trades

    def test_get_open_trades_maps_to_broker_orders(self):
        adapter, client = _adapter_with_mock_client()
        mock_fill = SimpleNamespace(
            execution=SimpleNamespace(shares=10.0, avgPrice=150.0, time="2026-01-01T10:00:00"),
            commissionReport=SimpleNamespace(commission=1.0),
        )
        mock_trade = SimpleNamespace(
            order=SimpleNamespace(orderId=55, action="BUY", totalQuantity=10.0, lmtPrice=0.0),
            orderStatus=SimpleNamespace(status="Submitted", filled=0.0, avgFillPrice=0.0),
            contract=SimpleNamespace(symbol="AAPL"),
            fills=[mock_fill],
        )
        client.trades.return_value = [mock_trade]

        result = adapter.get_open_trades()
        assert len(result) == 1
        assert result[0].broker_order_id == "55"
        assert result[0].ticker == "AAPL"
        assert result[0].status == OrderStatus.SUBMITTED
        assert len(result[0].fills) == 1


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

        client.connect()

        assert client.is_connected() is True
        assert calls == ["/iserver/auth/status", "/portfolio/accounts", "/iserver/accounts"]

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
            httpx.Response(200, json={"order_id": "42", "order_status": "Submitted"}),
        ]
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(f"{request.method} {request.url.path}")
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


class TestInteractiveBrokersWebAdapter:
    def _make_client(self) -> MagicMock:
        client = MagicMock()
        client.is_connected.return_value = True
        return client

    def test_place_order_submits_web_order(self):
        client = self._make_client()
        client.resolve_conid.return_value = "265598"
        client.submit_order.return_value = {"order_id": "123", "order_status": "Submitted"}
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.place_order(_make_order(order_type=OrderType.MARKET))

        assert result.broker_order_id == "123"
        assert result.status == OrderStatus.SUBMITTED
        client.submit_order.assert_called_once()

    def test_get_account_info_maps_ledger_and_summary(self):
        client = self._make_client()
        client.fetch_ledger.return_value = {
            "BASE": {
                "cashbalance": 50000.0,
                "stockmarketvalue": 12000.0,
                "netliquidationvalue": 62000.0,
            }
        }
        client.fetch_summary.return_value = {
            "buyingpower": {"amount": 100000.0},
            "netliquidation": {"amount": 62000.0},
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_account_info()

        assert result == {
            "TotalCashValue": 50000.0,
            "BuyingPower": 100000.0,
            "GrossPositionValue": 12000.0,
            "NetLiquidation": 62000.0,
        }

    def test_get_quotes_maps_snapshot_fields(self):
        client = self._make_client()
        client.resolve_conid.side_effect = ["265598", "8314"]
        client.fetch_marketdata_snapshot.return_value = [
            {"conid": 265598, "31": "168.42", "84": "168.41", "86": "168.43"},
            {"conid": 8314, "31": "189.60", "84": "189.56", "86": "189.61"},
        ]
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_quotes(["AAPL", "IBM"])

        assert result == {
            "AAPL": {"bid": 168.41, "ask": 168.43, "last": 168.42},
            "IBM": {"bid": 189.56, "ask": 189.61, "last": 189.6},
        }

    def test_get_open_trades_creates_synthetic_fill(self):
        client = self._make_client()
        client.fetch_orders.return_value = [
            {
                "orderId": 55,
                "ticker": "AAPL",
                "side": "BUY",
                "totalSize": 10,
                "filledQuantity": 10,
                "avgPrice": "151.25",
                "status": "Filled",
                "lastExecutionTime": "231211180049",
            }
        ]
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_open_trades()

        assert len(result) == 1
        assert result[0].status == OrderStatus.FILLED
        assert result[0].fills[0].exec_id == "web-55-10.0-231211180049"


# ---------------------------------------------------------------------------
# IbApiClient stub
# ---------------------------------------------------------------------------


class TestIbApiClient:
    def test_all_methods_raise_not_implemented(self):
        client = IbApiClient()
        with pytest.raises(NotImplementedError):
            client.connect("127.0.0.1", 7497, client_id=1)
        with pytest.raises(NotImplementedError):
            client.disconnect()
        with pytest.raises(NotImplementedError):
            client.is_connected()
        with pytest.raises(NotImplementedError):
            client.trades()

    def test_make_stock_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            IbApiClient().make_stock("AAPL")

    def test_make_order_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            IbApiClient().make_order(action="BUY", totalQuantity=10, orderType="MKT")

    def test_isinstance_check_passes_with_all_stubs(self):
        """IbApiClient must satisfy IBClientProtocol at runtime."""
        assert isinstance(IbApiClient(), IBClientProtocol)


# ---------------------------------------------------------------------------
# _map_ib_status
# ---------------------------------------------------------------------------


class TestMapIbStatus:
    @pytest.mark.parametrize("ib_status,expected", [
        ("Filled", OrderStatus.FILLED),
        ("PartiallyFilled", OrderStatus.PARTIALLY_FILLED),
        ("Submitted", OrderStatus.SUBMITTED),
        ("PreSubmitted", OrderStatus.SUBMITTED),
        ("Cancelled", OrderStatus.CANCELLED),
        ("ApiCancelled", OrderStatus.CANCELLED),
        ("PendingSubmit", OrderStatus.PENDING),
        ("Inactive", OrderStatus.REJECTED),
        ("UnknownStatus", OrderStatus.SUBMITTED),  # default
    ])
    def test_maps_correctly(self, ib_status, expected):
        assert _map_ib_status(ib_status) == expected


# ---------------------------------------------------------------------------
# Live trading safety invariants
# ---------------------------------------------------------------------------


class TestLiveTradingSafety:
    """These tests enforce the live_trading_enabled safety contract."""

    def test_paper_adapter_never_requires_live_enabled(self):
        """Paper accounts work regardless of live_trading_enabled value."""
        for flag in (0, None):
            broker = get_broker_for_account(_make_account(broker_type="paper", live_trading_enabled=flag))
            assert isinstance(broker, PaperBrokerAdapter)

    def test_ib_adapter_blocked_when_flag_is_zero(self):
        for flag in (0, "0", None, False):
            account = _make_account(broker_type="interactive_brokers", live_trading_enabled=flag)
            with pytest.raises(LiveTradingNotEnabledError):
                get_broker_for_account(account)

    def test_live_trading_not_enabled_error_is_runtime_error(self):
        """LiveTradingNotEnabledError must not be accidentally caught by broad except clauses."""
        assert issubclass(LiveTradingNotEnabledError, RuntimeError)


# ---------------------------------------------------------------------------
# reconcile_open_ib_orders
# ---------------------------------------------------------------------------


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _insert_account_row(conn, account_id: int = 1, name: str = "test-account") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO accounts (id, name, strategy, initial_cash, created_at) "
        "VALUES (?, ?, 'growth', 10000, '2024-01-01T00:00:00')",
        (account_id, name),
    )
    conn.commit()


def _insert_open_broker_order(conn, broker_order_id: str, account_id: int = 1) -> None:
    conn.execute(
        "INSERT INTO broker_orders "
        "(account_id, ticker, side, qty, requested_price, broker_order_id, status, submitted_at, updated_at) "
        "VALUES (?, 'AAPL', 'buy', 10, 150.0, ?, 'SUBMITTED', '2024-01-01T00:00:00', '2024-01-01T00:00:00')",
        (account_id, broker_order_id),
    )
    conn.commit()


class TestReconcileOpenIbOrders:
    """reconcile_open_ib_orders polls IB for fills on open SUBMITTED orders."""

    def test_non_ib_broker_returns_zero(self):
        from trading.services.auto_trader_runtime_service import reconcile_open_ib_orders

        conn = _make_db()
        account = _make_account(broker_type="paper")
        with patch("trading.services.auto_trader_runtime_service.get_broker_for_account") as mock_factory:
            mock_factory.return_value = PaperBrokerAdapter()
            result = reconcile_open_ib_orders(conn, "test-account", account, fee=0.0)
        assert result == 0

    def test_newly_filled_order_increments_count(self):
        from trading.services.auto_trader_runtime_service import reconcile_open_ib_orders

        conn = _make_db()
        _insert_account_row(conn)
        _insert_open_broker_order(conn, broker_order_id="42")

        account = _make_account(broker_type="interactive_brokers", id=1)
        fill = OrderFill(filled_qty=10.0, fill_price=151.0, fill_time="2024-01-02T10:00:00", commission=0.5, exec_id="exec-001")
        filled_order = BrokerOrder(
            account_id=1, ticker="AAPL", side="buy", qty=10.0, price=150.0,
            broker_order_id="42", status=OrderStatus.FILLED,
            filled_qty=10.0, avg_fill_price=151.0, commission=0.5,
            fills=[fill],
        )

        class _FakeIbAdapter(InteractiveBrokersAdapter):
            def __init__(self):
                pass

            def get_open_trades(self):
                return [filled_order]

            def disconnect(self):
                pass

        recorded = []
        with (
            patch("trading.services.auto_trader_runtime_service.get_broker_for_account", return_value=_FakeIbAdapter()),
            patch("trading.services.auto_trader_runtime_service.record_trade", lambda conn, **kw: recorded.append(kw)),
        ):
            count = reconcile_open_ib_orders(conn, "test-account", account, fee=1.0)

        assert count == 1
        assert len(recorded) == 1
        assert recorded[0]["ticker"] == "AAPL"
        assert recorded[0]["price"] == 151.0

    def test_duplicate_fill_is_idempotent(self):
        """Calling reconcile twice with the same exec_id inserts only one fill row."""
        from trading.services.auto_trader_runtime_service import reconcile_open_ib_orders

        conn = _make_db()
        _insert_account_row(conn)
        _insert_open_broker_order(conn, broker_order_id="99")

        account = _make_account(broker_type="interactive_brokers", id=1)
        fill = OrderFill(filled_qty=10.0, fill_price=152.0, fill_time="2024-01-02T10:00:00", commission=0.0, exec_id="exec-dup")
        partial_order = BrokerOrder(
            account_id=1, ticker="AAPL", side="buy", qty=10.0, price=150.0,
            broker_order_id="99", status=OrderStatus.SUBMITTED,
            filled_qty=5.0, avg_fill_price=152.0, commission=0.0,
            fills=[fill],
        )

        class _FakeIbAdapter(InteractiveBrokersAdapter):
            def __init__(self):
                pass

            def get_open_trades(self):
                return [partial_order]

            def disconnect(self):
                pass

        with patch("trading.services.auto_trader_runtime_service.get_broker_for_account", return_value=_FakeIbAdapter()):
            reconcile_open_ib_orders(conn, "test-account", account, fee=0.0)
            reconcile_open_ib_orders(conn, "test-account", account, fee=0.0)

        fills_count = conn.execute("SELECT COUNT(*) FROM order_fills WHERE exec_id = 'exec-dup'").fetchone()[0]
        assert fills_count == 1, "Duplicate exec_id fill must be inserted only once"

    def test_disconnect_called_even_when_no_open_orders(self):
        """Broker.disconnect() must still be called when no open orders are found."""
        from trading.services.auto_trader_runtime_service import reconcile_open_ib_orders

        conn = _make_db()
        _insert_account_row(conn)
        # No open broker orders inserted

        account = _make_account(broker_type="interactive_brokers", id=1)

        # Subclass so isinstance(broker, InteractiveBrokersAdapter) passes.
        class _FakeAdapter(InteractiveBrokersAdapter):
            def __init__(self):
                pass  # skip super().__init__

            def get_open_trades(self):
                return []

            def disconnect(self):
                _FakeAdapter._disconnect_calls += 1

            _disconnect_calls = 0

        fake_adapter = _FakeAdapter()
        with patch("trading.services.auto_trader_runtime_service.get_broker_for_account", return_value=fake_adapter):
            result = reconcile_open_ib_orders(conn, "test-account", account, fee=0.0)

        assert result == 0
        assert _FakeAdapter._disconnect_calls == 1
