"""IBKR socket/TWS adapter and client coverage."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from infrastructure.brokers.factory import LiveTradingNotEnabledError, get_broker_for_account
from infrastructure.brokers.ibkr_socket.adapter import IbkrSocketAdapter, _map_ib_status
from infrastructure.brokers.ibkr_socket.contracts import (
    IbkrAccountValue,
    IbkrFill,
    IbkrOrderRequest,
    IbkrPosition,
    IbkrQuote,
    IbkrTrade,
)
from infrastructure.brokers.ibkr_socket.ib_async_client import IbAsyncClient
from infrastructure.brokers.ibkr_socket.ibapi_client import IbApiClient
from infrastructure.brokers.ibkr_socket.protocol import IbkrSocketClient
from tests.support.account_records import make_account_record
from trading.models.orders.broker_order import BrokerOrder, OrderStatus, OrderType


def _make_account(**kwargs):
    return make_account_record(**kwargs)


def _make_order(**kwargs) -> BrokerOrder:
    defaults = dict(account_id=1, ticker="AAPL", side="buy", qty=10.0, price=150.0)
    defaults.update(kwargs)
    return BrokerOrder(**defaults)


def _mock_ib_client() -> MagicMock:
    client = MagicMock()
    client.is_connected.return_value = True
    return client


def _adapter_with_mock_client() -> tuple[IbkrSocketAdapter, MagicMock]:
    client = _mock_ib_client()
    adapter = IbkrSocketAdapter(client=client, host="127.0.0.1", port=7497, client_id=1)
    return adapter, client


def _socket_trade(**overrides) -> IbkrTrade:
    values = {
        "order_id": 42,
        "symbol": "AAPL",
        "action": "BUY",
        "total_quantity": 10.0,
        "limit_price": 0.0,
        "status": "Submitted",
        "filled": 0.0,
        "avg_fill_price": 0.0,
    }
    values.update(overrides)
    return IbkrTrade(**values)


class TestIbkrSocketFactoryRouting:
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
            patch("infrastructure.brokers.factory._require_live_trading_enabled"),
            patch("infrastructure.brokers.ibkr_socket.factory.IbAsyncClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, IbkrSocketAdapter)
        mock_client.connect.assert_called_once_with("127.0.0.1", 7497, client_id=1)

    def test_live_trading_enabled_missing_key_treated_as_disabled(self):
        account = _make_account(name="old-account", broker_type="interactive_brokers")
        with pytest.raises(LiveTradingNotEnabledError):
            get_broker_for_account(account)

    def test_live_trading_enabled_one_is_accepted(self):
        account = _make_account(
            broker_type="interactive_brokers",
            live_trading_enabled=1,
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        with patch("infrastructure.brokers.ibkr_socket.factory.IbAsyncClient", return_value=mock_client):
            broker = get_broker_for_account(account)
        assert isinstance(broker, IbkrSocketAdapter)

    def test_ibapi_backend_uses_ib_api_client(self):
        import infrastructure.brokers.ibkr_socket.factory as socket_factory_module

        account = _make_account(
            broker_type="interactive_brokers",
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        original = socket_factory_module.IBKR_SOCKET_CLIENT_BACKEND
        try:
            socket_factory_module.IBKR_SOCKET_CLIENT_BACKEND = "ibapi"
            with (
                patch("infrastructure.brokers.factory._require_live_trading_enabled"),
                patch("infrastructure.brokers.ibkr_socket.factory.IbApiClient", return_value=mock_client),
            ):
                broker = get_broker_for_account(account)
            assert isinstance(broker, IbkrSocketAdapter)
        finally:
            socket_factory_module.IBKR_SOCKET_CLIENT_BACKEND = original

    def test_unknown_ib_backend_raises_value_error(self):
        import infrastructure.brokers.ibkr_socket.factory as socket_factory_module

        account = _make_account(broker_type="interactive_brokers")
        original = socket_factory_module.IBKR_SOCKET_CLIENT_BACKEND
        try:
            socket_factory_module.IBKR_SOCKET_CLIENT_BACKEND = "not_a_real_backend"
            with patch("infrastructure.brokers.factory._require_live_trading_enabled"):
                with pytest.raises(ValueError, match="Unknown IBKR_SOCKET_CLIENT_BACKEND"):
                    get_broker_for_account(account)
        finally:
            socket_factory_module.IBKR_SOCKET_CLIENT_BACKEND = original


class TestIbkrSocketAdapter:
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

    def test_place_order_returns_submitted_status(self):
        adapter, client = _adapter_with_mock_client()
        client.place_order.return_value = _socket_trade()

        result = adapter.place_order(_make_order())

        assert result.status == OrderStatus.SUBMITTED
        assert result.broker_order_id == "42"
        assert result.submitted_at is not None

    def test_place_order_market_sends_mkt_type(self):
        adapter, client = _adapter_with_mock_client()
        client.place_order.return_value = _socket_trade(order_id=1)

        adapter.place_order(_make_order(order_type=OrderType.MARKET))

        request = client.place_order.call_args.args[0]
        assert request.order_type == "MKT"
        assert request.symbol == "AAPL"

    def test_place_order_limit_sends_lmt_type_and_price(self):
        adapter, client = _adapter_with_mock_client()
        client.place_order.return_value = _socket_trade(order_id=2)

        adapter.place_order(_make_order(order_type=OrderType.LIMIT, price=148.0))

        request = client.place_order.call_args.args[0]
        assert request.order_type == "LMT"
        assert request.limit_price == 148.0

    def test_cancel_order_calls_client_cancel(self):
        adapter, client = _adapter_with_mock_client()

        adapter.cancel_order("99")
        client.cancel_order.assert_called_once_with(99)

    def test_get_positions_returns_symbol_qty_dict(self):
        adapter, client = _adapter_with_mock_client()
        client.positions.return_value = [
            IbkrPosition(symbol="AAPL", quantity=10.0),
            IbkrPosition(symbol="MSFT", quantity=5.0),
        ]

        assert adapter.get_positions() == {"AAPL": 10.0, "MSFT": 5.0}

    def test_get_account_info_filters_to_known_usd_tags(self):
        adapter, client = _adapter_with_mock_client()
        summary = [
            IbkrAccountValue(tag="TotalCashValue", value="50000.0", currency="USD"),
            IbkrAccountValue(tag="BuyingPower", value="100000.0", currency="USD"),
            IbkrAccountValue(tag="SomeOtherTag", value="999.0", currency="USD"),
            IbkrAccountValue(tag="TotalCashValue", value="45000.0", currency="EUR"),
        ]
        client.account_summary.return_value = summary

        result = adapter.get_account_info()
        assert result["TotalCashValue"] == 50000.0
        assert result["BuyingPower"] == 100000.0
        assert "SomeOtherTag" not in result

    def test_get_quotes_returns_bid_ask_last(self):
        adapter, client = _adapter_with_mock_client()
        client.quotes.return_value = [
            IbkrQuote(symbol="AAPL", bid=149.0, ask=150.0, last=149.5)
        ]

        result = adapter.get_quotes(["AAPL"])
        assert result == {"AAPL": {"bid": 149.0, "ask": 150.0, "last": 149.5}}
        client.quotes.assert_called_once_with(["AAPL"])

    def test_get_open_trades_maps_to_broker_orders(self):
        adapter, client = _adapter_with_mock_client()
        client.trades.return_value = [
            _socket_trade(
                order_id=55,
                fills=(
                    IbkrFill(
                        shares=10.0,
                        price=150.0,
                        time="2026-01-01T10:00:00",
                        commission=1.0,
                    ),
                ),
            )
        ]

        result = adapter.get_open_trades()
        assert len(result) == 1
        assert result[0].broker_order_id == "55"
        assert result[0].ticker == "AAPL"
        assert result[0].status == OrderStatus.SUBMITTED
        assert len(result[0].fills) == 1

    def test_get_open_trades_captures_advanced_rejection_payload(self):
        adapter, client = _adapter_with_mock_client()
        client.trades.return_value = [
            _socket_trade(
                order_id=55,
                status="Inactive",
                status_reason='{"errorCode":"IBDBUYTX","errorMessage":"Trading restricted"}',
            )
        ]

        result = adapter.get_open_trades()

        assert result[0].status == OrderStatus.REJECTED
        assert result[0].status_reason == (
            '{"errorCode":"IBDBUYTX","errorMessage":"Trading restricted"}'
        )

    def test_get_open_trades_captures_latest_structured_order_error(self):
        adapter, client = _adapter_with_mock_client()
        client.trades.return_value = [
            _socket_trade(
                order_id=55,
                status="Cancelled",
                status_reason="IBKR 201: Order rejected",
            )
        ]

        result = adapter.get_open_trades()

        assert result[0].status == OrderStatus.CANCELLED
        assert result[0].status_reason == "IBKR 201: Order rejected"


class TestIbAsyncClient:
    def test_async_client_normalizes_ib_async_backend(self, monkeypatch):
        backend = MagicMock()
        backend.isConnected.return_value = True
        sdk_trade = SimpleNamespace(
            order=SimpleNamespace(orderId=42, action="BUY", totalQuantity=10.0, lmtPrice=0.0),
            orderStatus=SimpleNamespace(status="Submitted", filled=0.0, avgFillPrice=0.0),
            contract=SimpleNamespace(symbol="AAPL"),
            fills=[],
            advancedError="",
            log=[],
        )
        backend.placeOrder.return_value = sdk_trade
        backend.trades.return_value = [sdk_trade]
        backend.positions.return_value = [
            SimpleNamespace(contract=SimpleNamespace(symbol="AAPL"), position=3.0)
        ]
        backend.accountSummary.return_value = [
            SimpleNamespace(tag="NetLiquidation", value="1000", currency="USD")
        ]
        backend.reqTickers.return_value = [
            SimpleNamespace(
                contract=SimpleNamespace(symbol="AAPL"),
                bid=149.0,
                ask=150.0,
                last=149.5,
            )
        ]
        fake_module = SimpleNamespace(
            IB=MagicMock(return_value=backend),
            Stock=MagicMock(return_value="stock-contract"),
            Order=MagicMock(return_value="order-object"),
        )
        monkeypatch.setitem(sys.modules, "ib_async", fake_module)

        client = IbAsyncClient()
        order_request = IbkrOrderRequest(
            symbol="AAPL",
            action="BUY",
            total_quantity=10.0,
            order_type="MKT",
            limit_price=0.0,
            time_in_force="DAY",
        )

        client.connect("127.0.0.1", 7497, client_id=7)
        assert client.is_connected() is True
        assert client.place_order(order_request).order_id == 42
        client.cancel_order(42)
        assert client.trades()[0].symbol == "AAPL"
        assert client.positions() == [IbkrPosition(symbol="AAPL", quantity=3.0)]
        assert client.account_summary() == [
            IbkrAccountValue(tag="NetLiquidation", value="1000", currency="USD")
        ]
        assert client.quotes(["AAPL"]) == [
            IbkrQuote(symbol="AAPL", bid=149.0, ask=150.0, last=149.5)
        ]
        client.disconnect()

        backend.connect.assert_called_once_with("127.0.0.1", 7497, clientId=7)
        backend.disconnect.assert_called_once_with()
        backend.cancelOrder.assert_called_once_with(sdk_trade.order)
        assert fake_module.Stock.call_args_list == [
            call("AAPL", "SMART", "USD"),
            call("AAPL", "SMART", "USD"),
        ]
        fake_module.Order.assert_called_once_with(
            action="BUY",
            totalQuantity=10.0,
            orderType="MKT",
            lmtPrice=0.0,
            tif="DAY",
        )


class TestIbApiClient:
    def test_all_methods_raise_not_implemented(self):
        client = IbApiClient()
        order_request = IbkrOrderRequest(
            symbol="AAPL",
            action="BUY",
            total_quantity=10.0,
            order_type="MKT",
            limit_price=0.0,
            time_in_force="DAY",
        )
        with pytest.raises(NotImplementedError):
            client.connect("127.0.0.1", 7497, client_id=1)
        with pytest.raises(NotImplementedError):
            client.disconnect()
        with pytest.raises(NotImplementedError):
            client.is_connected()
        with pytest.raises(NotImplementedError):
            client.place_order(order_request)
        with pytest.raises(NotImplementedError):
            client.cancel_order(1)
        with pytest.raises(NotImplementedError):
            client.trades()
        with pytest.raises(NotImplementedError):
            client.positions()
        with pytest.raises(NotImplementedError):
            client.account_summary()
        with pytest.raises(NotImplementedError):
            client.quotes(["AAPL"])

    def test_isinstance_check_passes_with_all_stubs(self):
        assert isinstance(IbApiClient(), IbkrSocketClient)


class TestIbkrSocketStatusMap:
    @pytest.mark.parametrize(
        "ib_status,expected",
        [
            ("Filled", OrderStatus.FILLED),
            ("PartiallyFilled", OrderStatus.PARTIALLY_FILLED),
            ("Submitted", OrderStatus.SUBMITTED),
            ("PreSubmitted", OrderStatus.SUBMITTED),
            ("Cancelled", OrderStatus.CANCELLED),
            ("ApiCancelled", OrderStatus.CANCELLED),
            ("PendingSubmit", OrderStatus.PENDING),
            ("Inactive", OrderStatus.REJECTED),
            ("UnknownStatus", OrderStatus.SUBMITTED),
        ],
    )
    def test_maps_correctly(self, ib_status, expected):
        assert _map_ib_status(ib_status) == expected


class TestIbkrSocketLiveTradingSafety:
    def test_ib_adapter_blocked_when_flag_is_zero(self):
        for flag in (0, "0", None, False):
            account = _make_account(broker_type="interactive_brokers", live_trading_enabled=flag)
            with pytest.raises(LiveTradingNotEnabledError):
                get_broker_for_account(account)
