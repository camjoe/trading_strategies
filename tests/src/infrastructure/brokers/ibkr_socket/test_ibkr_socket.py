"""IBKR socket/TWS adapter and client coverage."""

from __future__ import annotations

import sys
import threading
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
from infrastructure.brokers.ibkr_socket.ibapi_client import (
    IbApiClient,
    _build_native_app,
    _IbApiCallbackState,
    _parse_error_callback,
)
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
    def test_native_app_builds_stock_order_and_binds_callbacks(self, monkeypatch):
        class FakeWrapper:
            def __init__(self):
                pass

        class FakeClient:
            def __init__(self, wrapper):
                self.wrapper = wrapper
                self.placed = None
                self.cancelled = None
                self.open_orders_requested = False
                self.positions_requested = False
                self.positions_cancelled = False
                self.account_summary_requested = None
                self.account_summary_cancelled = None

            def placeOrder(self, order_id, contract, order):
                self.placed = (order_id, contract, order)

            def cancelOrder(self, order_id, cancel):
                self.cancelled = (order_id, cancel)

            def reqOpenOrders(self):
                self.open_orders_requested = True

            def reqPositions(self):
                self.positions_requested = True

            def cancelPositions(self):
                self.positions_cancelled = True

            def reqAccountSummary(self, request_id, group, tags):
                self.account_summary_requested = (request_id, group, tags)

            def cancelAccountSummary(self, request_id):
                self.account_summary_cancelled = request_id

        class FakeContract:
            pass

        class FakeOrder:
            pass

        class FakeOrderCancel:
            pass

        monkeypatch.setitem(sys.modules, "ibapi", SimpleNamespace())
        monkeypatch.setitem(sys.modules, "ibapi.client", SimpleNamespace(EClient=FakeClient))
        monkeypatch.setitem(sys.modules, "ibapi.wrapper", SimpleNamespace(EWrapper=FakeWrapper))
        monkeypatch.setitem(sys.modules, "ibapi.contract", SimpleNamespace(Contract=FakeContract))
        monkeypatch.setitem(sys.modules, "ibapi.order", SimpleNamespace(Order=FakeOrder))
        monkeypatch.setitem(
            sys.modules,
            "ibapi.order_cancel",
            SimpleNamespace(OrderCancel=FakeOrderCancel),
        )
        callbacks = _IbApiCallbackState()
        app = _build_native_app(callbacks)
        request = IbkrOrderRequest(
            symbol="AAPL",
            action="BUY",
            total_quantity=10.0,
            order_type="LMT",
            limit_price=150.0,
            time_in_force="DAY",
        )

        app.place_order(42, request)
        app.cancel_order(42)
        app.request_open_orders()
        app.request_positions()
        app.cancel_positions()
        app.request_account_summary(7, "All", "NetLiquidation")
        app.cancel_account_summary(7)
        app.openOrder(
            42,
            SimpleNamespace(symbol="AAPL"),
            SimpleNamespace(action="BUY", totalQuantity=10.0, lmtPrice=150.0),
            SimpleNamespace(status="Submitted"),
        )
        app.orderStatus(42, "Filled", 10.0, 0.0, 149.5, 1, 0, 149.5, 1, "")
        app.execDetails(
            1,
            SimpleNamespace(symbol="AAPL"),
            SimpleNamespace(
                orderId=42,
                execId="exec-1",
                shares=10.0,
                price=149.5,
                time="2026-07-24T12:00:00Z",
            ),
        )
        app.commissionReport(SimpleNamespace(execId="exec-1", commission=1.25))
        app.position(
            "U1",
            SimpleNamespace(symbol="AAPL"),
            3.0,
            149.5,
        )
        app.positionEnd()
        callbacks.begin_account_summary(7)
        app.accountSummary(7, "U1", "NetLiquidation", "1000", "USD")
        app.accountSummaryEnd(7)

        order_id, contract, native_order = app.placed
        assert order_id == 42
        assert (contract.symbol, contract.secType, contract.exchange, contract.currency) == (
            "AAPL",
            "STK",
            "SMART",
            "USD",
        )
        assert native_order.action == "BUY"
        assert native_order.totalQuantity == 10.0
        assert native_order.orderType == "LMT"
        assert native_order.lmtPrice == 150.0
        assert native_order.tif == "DAY"
        assert app.cancelled[0] == 42
        assert isinstance(app.cancelled[1], FakeOrderCancel)
        assert app.open_orders_requested is True
        assert app.positions_requested is True
        assert app.positions_cancelled is True
        assert app.account_summary_requested == (7, "All", "NetLiquidation")
        assert app.account_summary_cancelled == 7
        trade = callbacks.trades()[0]
        assert trade.status == "Filled"
        assert trade.fills[0].commission == 1.25
        assert callbacks.positions() == [IbkrPosition(symbol="AAPL", quantity=3.0)]
        assert callbacks.account_values() == [
            IbkrAccountValue(tag="NetLiquidation", value="1000", currency="USD")
        ]

    def test_connect_waits_for_readiness_and_reserves_monotonic_order_ids(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=100)
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)

        client.connect("127.0.0.1", 7497, client_id=7)

        assert client.is_connected() is True
        assert client._reserve_order_id() == 100
        assert client._reserve_order_id() == 101
        app = app_holder["app"]
        assert app.connect_args == ("127.0.0.1", 7497, 7)

        client.disconnect()

        assert client.is_connected() is False
        assert app.disconnect_calls == 1

    def test_connect_times_out_without_next_valid_id(self):
        client = IbApiClient(
            app_factory=lambda callbacks: _FakeNativeApp(callbacks),
            connection_timeout_seconds=0.01,
        )

        with pytest.raises(TimeoutError, match="nextValidId"):
            client.connect("127.0.0.1", 7497, client_id=1)

        assert client.is_connected() is False

    def test_message_loop_failure_propagates_from_connect(self):
        client = IbApiClient(
            app_factory=lambda callbacks: _FakeNativeApp(
                callbacks,
                run_error=ValueError("decoder failed"),
            )
        )

        with pytest.raises(RuntimeError, match="decoder failed"):
            client.connect("127.0.0.1", 7497, client_id=1)

    def test_callback_errors_are_immutable_snapshots(self):
        callback_holder = {}

        def app_factory(callbacks):
            callback_holder["callbacks"] = callbacks
            return _FakeNativeApp(callbacks, ready_order_id=1)

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)
        callbacks = callback_holder["callbacks"]
        callbacks.record_error(42, 201, "Order rejected", '{"reason":"margin"}')

        errors = client.callback_errors()

        assert len(errors) == 1
        assert errors[0].request_id == 42
        assert errors[0].code == 201
        assert errors[0].advanced_rejection == '{"reason":"margin"}'
        assert isinstance(errors, tuple)
        client.disconnect()

    def test_unexpected_connection_close_blocks_future_order_ids(self):
        callback_holder = {}

        def app_factory(callbacks):
            callback_holder["callbacks"] = callbacks
            return _FakeNativeApp(callbacks, ready_order_id=10)

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        callback_holder["callbacks"].record_connection_closed()

        with pytest.raises(RuntimeError, match="closed unexpectedly"):
            client._reserve_order_id()
        client.disconnect()

    def test_requested_disconnect_does_not_record_connection_failure(self):
        callback_holder = {}

        def app_factory(callbacks):
            callback_holder["callbacks"] = callbacks
            return _FakeNativeApp(callbacks, ready_order_id=10)

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)
        client.disconnect()

        callback_holder["callbacks"].record_connection_closed()

        assert client.callback_errors() == ()

    @pytest.mark.parametrize(
        "args,expected",
        [
            ((201, "Rejected"), (201, "Rejected", None)),
            ((201, "Rejected", '{"reason":"margin"}'), (201, "Rejected", '{"reason":"margin"}')),
            ((123456789, 201, "Rejected", ""), (201, "Rejected", None)),
        ],
    )
    def test_parse_error_callback_supports_native_signatures(self, args, expected):
        assert _parse_error_callback(args) == expected

    def test_place_order_reserves_id_and_returns_pending_trade(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=50)
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)
        order_request = IbkrOrderRequest(
            symbol="AAPL",
            action="BUY",
            total_quantity=10.0,
            order_type="MKT",
            limit_price=0.0,
            time_in_force="DAY",
        )

        trade = client.place_order(order_request)

        assert trade.order_id == 50
        assert trade.symbol == "AAPL"
        assert trade.status == "PendingSubmit"
        assert app_holder["app"].place_order_calls == [(50, order_request)]
        client.disconnect()

    def test_order_callbacks_produce_deduplicated_fill_and_commission(self):
        callback_holder = {}

        def app_factory(callbacks):
            callback_holder["callbacks"] = callbacks
            return _FakeNativeApp(callbacks, ready_order_id=50)

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)
        client.place_order(
            IbkrOrderRequest(
                symbol="AAPL",
                action="BUY",
                total_quantity=10.0,
                order_type="LMT",
                limit_price=150.0,
                time_in_force="DAY",
            )
        )
        callbacks = callback_holder["callbacks"]
        callbacks.record_order_status(50, "PartiallyFilled", 5.0, 149.5)
        callbacks.record_commission("exec-1", 1.25)
        callbacks.record_execution(50, "exec-1", 5.0, 149.5, "2026-07-24T12:00:00Z")
        callbacks.record_execution(50, "exec-1", 5.0, 149.5, "2026-07-24T12:00:00Z")

        trades = client.trades()

        assert len(trades) == 1
        assert trades[0].status == "PartiallyFilled"
        assert trades[0].filled == 5.0
        assert trades[0].avg_fill_price == 149.5
        assert len(trades[0].fills) == 1
        assert trades[0].fills[0].exec_id == "exec-1"
        assert trades[0].fills[0].commission == 1.25
        client.disconnect()

    def test_rejection_error_is_associated_with_order(self):
        callback_holder = {}

        def app_factory(callbacks):
            callback_holder["callbacks"] = callbacks
            return _FakeNativeApp(callbacks, ready_order_id=50)

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)
        client.place_order(
            IbkrOrderRequest(
                symbol="AAPL",
                action="BUY",
                total_quantity=10.0,
                order_type="MKT",
                limit_price=0.0,
                time_in_force="DAY",
            )
        )
        callbacks = callback_holder["callbacks"]
        callbacks.record_error(50, 201, "Order rejected", '{"reason":"margin"}')
        callbacks.record_order_status(50, "Inactive", 0.0, None)

        trade = client.trades()[0]

        assert trade.status == "Inactive"
        assert trade.status_reason == '{"reason":"margin"}'
        client.disconnect()

    def test_cancel_order_delegates_by_order_id(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=1)
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        client.cancel_order(99)

        assert app_holder["app"].cancel_order_calls == [99]
        client.disconnect()

    def test_trade_refresh_times_out_without_open_order_end(self):
        client = IbApiClient(
            app_factory=lambda callbacks: _FakeNativeApp(
                callbacks,
                ready_order_id=1,
                complete_open_orders=False,
            ),
            request_timeout_seconds=0.01,
        )
        client.connect("127.0.0.1", 7497, client_id=1)

        with pytest.raises(TimeoutError, match="openOrderEnd"):
            client.trades()
        client.disconnect()

    def test_positions_returns_sorted_deduplicated_records_and_cancels_subscription(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=1)
            app.positions_to_emit = [
                ("MSFT", 2.0),
                ("AAPL", 1.0),
                ("AAPL", 3.0),
            ]
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        positions = client.positions()

        assert positions == [
            IbkrPosition(symbol="AAPL", quantity=3.0),
            IbkrPosition(symbol="MSFT", quantity=2.0),
        ]
        assert app_holder["app"].position_requests == 1
        assert app_holder["app"].position_cancellations == 1
        client.disconnect()

    def test_positions_timeout_still_cancels_subscription(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(
                callbacks,
                ready_order_id=1,
                complete_positions=False,
            )
            app_holder["app"] = app
            return app

        client = IbApiClient(
            app_factory=app_factory,
            request_timeout_seconds=0.01,
        )
        client.connect("127.0.0.1", 7497, client_id=1)

        with pytest.raises(TimeoutError, match="positionEnd"):
            client.positions()

        assert app_holder["app"].position_cancellations == 1
        client.disconnect()

    def test_background_failure_wakes_position_request_and_cancels_subscription(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(
                callbacks,
                ready_order_id=1,
                complete_positions=False,
                request_error=RuntimeError("socket reader failed"),
            )
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        with pytest.raises(RuntimeError, match="socket reader failed"):
            client.positions()

        assert app_holder["app"].position_cancellations == 1
        client.disconnect()

    def test_account_summary_returns_records_and_uses_monotonic_request_ids(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=1)
            app.account_values_to_emit = [
                ("U1", "NetLiquidation", "1000", "USD"),
                ("U1", "BuyingPower", "2000", "USD"),
                ("U1", "BuyingPower", "2500", "USD"),
            ]
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        first = client.account_summary()
        second = client.account_summary()

        assert first == second
        assert first == [
            IbkrAccountValue(tag="BuyingPower", value="2500", currency="USD"),
            IbkrAccountValue(tag="NetLiquidation", value="1000", currency="USD"),
        ]
        app = app_holder["app"]
        assert [request[0] for request in app.account_summary_requests] == [1, 2]
        assert app.account_summary_cancellations == [1, 2]
        client.disconnect()

    def test_account_summary_timeout_still_cancels_request(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(
                callbacks,
                ready_order_id=1,
                complete_account_summary=False,
            )
            app_holder["app"] = app
            return app

        client = IbApiClient(
            app_factory=app_factory,
            request_timeout_seconds=0.01,
        )
        client.connect("127.0.0.1", 7497, client_id=1)

        with pytest.raises(TimeoutError, match="accountSummaryEnd"):
            client.account_summary()

        assert app_holder["app"].account_summary_cancellations == [1]
        client.disconnect()

    def test_unimplemented_data_operations_remain_explicit(self):
        client = IbApiClient(app_factory=lambda callbacks: _FakeNativeApp(callbacks))
        with pytest.raises(NotImplementedError):
            client.quotes(["AAPL"])

    def test_isinstance_check_passes_with_all_stubs(self):
        assert isinstance(
            IbApiClient(app_factory=lambda callbacks: _FakeNativeApp(callbacks)),
            IbkrSocketClient,
        )


class _FakeNativeApp:
    def __init__(
        self,
        callbacks,
        ready_order_id=None,
        run_error=None,
        complete_open_orders=True,
        complete_positions=True,
        complete_account_summary=True,
        request_error=None,
    ):
        self.callbacks = callbacks
        self.ready_order_id = ready_order_id
        self.run_error = run_error
        self.complete_open_orders = complete_open_orders
        self.complete_positions = complete_positions
        self.complete_account_summary = complete_account_summary
        self.request_error = request_error
        self.connected = False
        self.connect_args = None
        self.disconnect_calls = 0
        self.place_order_calls = []
        self.cancel_order_calls = []
        self.open_order_requests = 0
        self.position_requests = 0
        self.position_cancellations = 0
        self.account_summary_requests = []
        self.account_summary_cancellations = []
        self.positions_to_emit = []
        self.account_values_to_emit = []
        self._stop = threading.Event()

    def connect(self, host, port, clientId):
        self.connected = True
        self.connect_args = (host, port, clientId)
        if self.ready_order_id is not None:
            self.callbacks.record_next_order_id(self.ready_order_id)

    def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False
        self._stop.set()

    def isConnected(self):
        return self.connected

    def run(self):
        if self.run_error is not None:
            raise self.run_error
        self._stop.wait()

    def place_order(self, order_id, order):
        self.place_order_calls.append((order_id, order))

    def cancel_order(self, order_id):
        self.cancel_order_calls.append(order_id)

    def request_open_orders(self):
        self.open_order_requests += 1
        if self.complete_open_orders:
            self.callbacks.finish_open_order_refresh()

    def request_positions(self):
        self.position_requests += 1
        if self.request_error is not None:
            self.callbacks.record_background_error(self.request_error)
            return
        for symbol, quantity in self.positions_to_emit:
            self.callbacks.record_position(symbol, quantity)
        if self.complete_positions:
            self.callbacks.finish_positions()

    def cancel_positions(self):
        self.position_cancellations += 1

    def request_account_summary(self, request_id, group, tags):
        self.account_summary_requests.append((request_id, group, tags))
        for account, tag, value, currency in self.account_values_to_emit:
            self.callbacks.record_account_value(request_id, account, tag, value, currency)
        if self.complete_account_summary:
            self.callbacks.finish_account_summary(request_id)

    def cancel_account_summary(self, request_id):
        self.account_summary_cancellations.append(request_id)


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
