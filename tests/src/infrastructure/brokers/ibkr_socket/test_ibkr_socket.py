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
from trading.models.orders import OrderRequest, OrderStatus, OrderType


class _FakeStartupFetch:
    """Stand-in for `ib_async.StartupFetch`; the real one is an IntFlag."""

    POSITIONS = 1
    ORDERS_OPEN = 2
    ORDERS_COMPLETE = 4
    ACCOUNT_UPDATES = 8
    SUB_ACCOUNT_UPDATES = 16
    EXECUTIONS = 32


def _make_account(**kwargs):
    return make_account_record(**kwargs)


def _make_order(**kwargs) -> OrderRequest:
    defaults = dict(account_id=1, ticker="AAPL", side="buy", qty=10.0, price=150.0)
    defaults.update(kwargs)
    return OrderRequest(**defaults)


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
        account = _make_account(broker_type="interactive_brokers_socket", live_trading_enabled=0)
        with pytest.raises(LiveTradingNotEnabledError, match="live_trading_enabled"):
            get_broker_for_account(account)

    def test_ib_error_message_mentions_manual_requirement(self):
        account = _make_account(broker_type="interactive_brokers_socket", live_trading_enabled=0)
        with pytest.raises(LiveTradingNotEnabledError, match="manually"):
            get_broker_for_account(account)

    def test_ib_with_live_trading_enabled_connects(self):
        account = _make_account(
            broker_type="interactive_brokers_socket",
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
        account = _make_account(name="old-account", broker_type="interactive_brokers_socket")
        with pytest.raises(LiveTradingNotEnabledError):
            get_broker_for_account(account)

    def test_live_trading_enabled_one_is_accepted(self):
        account = _make_account(
            broker_type="interactive_brokers_socket",
            live_trading_enabled=1,
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        with patch("infrastructure.brokers.ibkr_socket.factory.IbAsyncClient", return_value=mock_client):
            broker = get_broker_for_account(account)
        assert isinstance(broker, IbkrSocketAdapter)

    def test_ibapi_backend_uses_ib_api_client(self, monkeypatch):
        account = _make_account(
            broker_type="interactive_brokers_socket",
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        monkeypatch.setenv("TRADING_IBKR_SOCKET_CLIENT_BACKEND", "ibapi")
        with (
            patch("infrastructure.brokers.factory._require_live_trading_enabled"),
            patch("infrastructure.brokers.ibkr_socket.factory.IbApiClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, IbkrSocketAdapter)

    def test_default_backend_uses_ib_async_when_environment_is_blank(self, monkeypatch):
        account = _make_account(broker_type="interactive_brokers_socket")
        mock_client = _mock_ib_client()
        monkeypatch.setenv("TRADING_IBKR_SOCKET_CLIENT_BACKEND", "  ")
        with (
            patch("infrastructure.brokers.factory._require_live_trading_enabled"),
            patch("infrastructure.brokers.ibkr_socket.factory.IbAsyncClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, IbkrSocketAdapter)

    def test_backend_environment_value_is_case_and_whitespace_insensitive(self, monkeypatch):
        account = _make_account(broker_type="interactive_brokers_socket")
        mock_client = _mock_ib_client()
        monkeypatch.setenv("TRADING_IBKR_SOCKET_CLIENT_BACKEND", " IBAPI ")
        with (
            patch("infrastructure.brokers.factory._require_live_trading_enabled"),
            patch("infrastructure.brokers.ibkr_socket.factory.IbApiClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, IbkrSocketAdapter)

    def test_unknown_ib_backend_raises_value_error(self, monkeypatch):
        account = _make_account(broker_type="interactive_brokers_socket")
        monkeypatch.setenv("TRADING_IBKR_SOCKET_CLIENT_BACKEND", "not_a_real_backend")
        with patch("infrastructure.brokers.factory._require_live_trading_enabled"):
            with pytest.raises(ValueError, match="TRADING_IBKR_SOCKET_CLIENT_BACKEND"):
                get_broker_for_account(account)


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

    def test_managed_accounts_delegates_to_client(self):
        adapter, client = _adapter_with_mock_client()
        client.managed_accounts.return_value = ["DU1234567"]
        assert adapter.managed_accounts() == ["DU1234567"]

    def test_managed_accounts_requires_a_connection(self):
        """The socket only knows its accounts once IBKR has reported them."""
        adapter, client = _adapter_with_mock_client()
        client.is_connected.return_value = False
        with pytest.raises(RuntimeError, match="not connected"):
            adapter.managed_accounts()

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

    def test_place_order_sends_the_client_order_id_as_order_ref(self):
        """IB's orderRef is how a socket order is recognized if its answer is lost."""
        adapter, client = _adapter_with_mock_client()
        client.place_order.return_value = _socket_trade(order_id=3)

        adapter.place_order(_make_order(client_order_id="ts-AAPL-BUY-1"))

        assert client.place_order.call_args.args[0].order_ref == "ts-AAPL-BUY-1"

    def test_open_trades_carry_the_echoed_order_ref_as_client_order_id(self):
        adapter, client = _adapter_with_mock_client()
        client.trades.return_value = [
            _socket_trade(order_id=56, order_ref="ts-AAPL-BUY-2"),
            # Placed outside this system: IB reports no ref, and nothing is invented.
            _socket_trade(order_id=57, order_ref=""),
        ]

        result = adapter.get_open_trades()

        assert [order.client_order_id for order in result] == ["ts-AAPL-BUY-2", None]

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
        client.quotes.return_value = [IbkrQuote(symbol="AAPL", bid=149.0, ask=150.0, last=149.5)]

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
        assert result[0].status_reason == ('{"errorCode":"IBDBUYTX","errorMessage":"Trading restricted"}')

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
    def test_quotes_skip_a_ticker_whose_contract_did_not_qualify(self, monkeypatch):
        """One unqualified symbol must not take the whole batch down.

        `reqTickers` returns a ticker with no contract when qualification
        failed. Reading `.symbol` off it raised AttributeError, which lost the
        quotes for every symbol that did resolve.
        """
        backend = MagicMock()
        good = SimpleNamespace(contract=SimpleNamespace(symbol="AAPL"), bid=1.0, ask=2.0, last=1.5)
        unqualified = SimpleNamespace(contract=None, bid=0.0, ask=0.0, last=0.0)
        backend.reqTickers.return_value = [unqualified, good]
        monkeypatch.setitem(
            sys.modules, "ib_async", SimpleNamespace(IB=MagicMock(return_value=backend), Stock=MagicMock())
        )

        quotes = IbAsyncClient().quotes(["BADSYM", "AAPL"])

        assert [quote.symbol for quote in quotes] == ["AAPL"]

    def test_async_client_normalizes_ib_async_backend(self, monkeypatch):
        backend = MagicMock()
        backend.isConnected.return_value = True
        sdk_trade = SimpleNamespace(
            order=SimpleNamespace(
                orderId=42, action="BUY", totalQuantity=10.0, lmtPrice=0.0, orderRef="ts-AAPL-BUY-1"
            ),
            orderStatus=SimpleNamespace(status="Submitted", filled=0.0, avgFillPrice=0.0),
            contract=SimpleNamespace(symbol="AAPL"),
            fills=[],
            advancedError="",
            log=[],
        )
        backend.placeOrder.return_value = sdk_trade
        backend.trades.return_value = [sdk_trade]
        backend.positions.return_value = [SimpleNamespace(contract=SimpleNamespace(symbol="AAPL"), position=3.0)]
        backend.accountSummary.return_value = [SimpleNamespace(tag="NetLiquidation", value="1000", currency="USD")]
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
            StartupFetch=_FakeStartupFetch,
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
            order_ref="ts-AAPL-BUY-1",
        )

        client.connect("127.0.0.1", 7497, client_id=7)
        assert client.is_connected() is True
        assert client.place_order(order_request).order_id == 42
        client.cancel_order(42)
        assert client.trades()[0].symbol == "AAPL"
        # IB echoes orderRef; reconciliation matches a pending row on it.
        assert client.trades()[0].order_ref == "ts-AAPL-BUY-1"
        assert client.positions() == [IbkrPosition(symbol="AAPL", quantity=3.0)]
        assert client.account_summary() == [IbkrAccountValue(tag="NetLiquidation", value="1000", currency="USD")]
        assert client.quotes(["AAPL"]) == [IbkrQuote(symbol="AAPL", bid=149.0, ask=150.0, last=149.5)]
        client.disconnect()

        # Connect kwargs are asserted in TestIbAsyncConnect; here only the
        # target matters.
        assert backend.connect.call_args.args == ("127.0.0.1", 7497)
        assert backend.connect.call_args.kwargs["clientId"] == 7
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
            orderRef="ts-AAPL-BUY-1",
        )


class TestIbAsyncConnect:
    """The startup sync fills the caches `trades()` and `positions()` read.

    ib_async logs a sync timeout and connects anyway, which would leave
    `trades()` empty in a way reconciliation cannot distinguish from "no open
    orders". Observed against a real IB Gateway, whose sync exceeded the 4s
    default.
    """

    @staticmethod
    def _connect_kwargs(monkeypatch) -> dict:
        backend = MagicMock()
        monkeypatch.setitem(
            sys.modules,
            "ib_async",
            SimpleNamespace(IB=MagicMock(return_value=backend), StartupFetch=_FakeStartupFetch),
        )
        IbAsyncClient().connect("127.0.0.1", 4002, client_id=7)
        return backend.connect.call_args.kwargs

    def test_sync_failures_are_raised_rather_than_logged(self, monkeypatch):
        assert self._connect_kwargs(monkeypatch)["raiseSyncErrors"] is True

    def test_connect_timeout_exceeds_the_ib_async_default(self, monkeypatch):
        assert self._connect_kwargs(monkeypatch)["timeout"] > 4

    def test_only_the_fields_this_client_reads_are_fetched(self, monkeypatch):
        # Completed orders and sub-account updates are never read, and each is
        # another request that can time out.
        fetch_fields = self._connect_kwargs(monkeypatch)["fetchFields"]
        assert fetch_fields & _FakeStartupFetch.ORDERS_OPEN
        assert fetch_fields & _FakeStartupFetch.EXECUTIONS
        assert not fetch_fields & _FakeStartupFetch.ORDERS_COMPLETE
        assert not fetch_fields & _FakeStartupFetch.SUB_ACCOUNT_UPDATES

    def test_host_port_and_client_id_are_still_forwarded(self, monkeypatch):
        backend = MagicMock()
        monkeypatch.setitem(
            sys.modules,
            "ib_async",
            SimpleNamespace(IB=MagicMock(return_value=backend), StartupFetch=_FakeStartupFetch),
        )
        IbAsyncClient().connect("10.0.0.5", 4002, client_id=7)
        args, kwargs = backend.connect.call_args
        assert args == ("10.0.0.5", 4002)
        assert kwargs["clientId"] == 7


class TestManagedAccounts:
    """Account identity is what the socket paper venue asserts on."""

    def test_ib_async_client_reports_trimmed_account_ids(self, monkeypatch):
        backend = MagicMock()
        backend.managedAccounts.return_value = [" DU1234567 ", "DU7654321", "", "   "]
        monkeypatch.setitem(sys.modules, "ib_async", SimpleNamespace(IB=MagicMock(return_value=backend)))

        assert IbAsyncClient().managed_accounts() == ["DU1234567", "DU7654321"]

    def test_callback_state_splits_the_comma_separated_list(self):
        callbacks = _IbApiCallbackState()
        callbacks.record_managed_accounts("DU1234567,DU7654321")
        assert callbacks.managed_accounts() == ["DU1234567", "DU7654321"]

    def test_callback_state_ignores_padding_and_empty_entries(self):
        callbacks = _IbApiCallbackState()
        callbacks.record_managed_accounts(" DU1234567 , ,DU7654321,")
        assert callbacks.managed_accounts() == ["DU1234567", "DU7654321"]

    def test_callback_state_reports_nothing_before_the_callback_arrives(self):
        assert _IbApiCallbackState().managed_accounts() == []

    def test_ibapi_client_waits_for_a_late_managed_accounts_callback(self):
        """`connect` only waits for nextValidId; managedAccounts may arrive after.

        Reading without waiting returns [], which the paper-venue guard cannot
        tell apart from a session with no accounts — so it would refuse a good
        paper account on whichever orderings IBKR happens to produce.
        """

        class _LateAccountsApp(_FakeNativeApp):
            def connect(self, host, port, clientId):
                super().connect(host, port, clientId)
                # nextValidId lands first and releases connect(); the account list
                # follows on the message loop a moment later.
                threading.Timer(0.05, lambda: self.callbacks.record_managed_accounts("DU1234567")).start()

        client = IbApiClient(app_factory=lambda callbacks: _LateAccountsApp(callbacks, ready_order_id=1))
        client.connect("127.0.0.1", 7497, client_id=1)
        try:
            assert client.managed_accounts() == ["DU1234567"]
        finally:
            client.disconnect()

    def test_ibapi_client_gives_up_waiting_and_reports_nothing(self):
        """A callback that never arrives must not hang; the caller fails closed."""
        client = IbApiClient(
            app_factory=lambda callbacks: _FakeNativeApp(callbacks, ready_order_id=1),
            request_timeout_seconds=0.05,
        )
        client.connect("127.0.0.1", 7497, client_id=1)
        try:
            assert client.managed_accounts() == []
        finally:
            client.disconnect()


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
                self.market_data_requested = None
                self.market_data_cancelled = None

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

            def reqMktData(
                self,
                request_id,
                contract,
                generic_ticks,
                snapshot,
                regulatory_snapshot,
                options,
            ):
                self.market_data_requested = (
                    request_id,
                    contract,
                    generic_ticks,
                    snapshot,
                    regulatory_snapshot,
                    options,
                )

            def cancelMktData(self, request_id):
                self.market_data_cancelled = request_id

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
            order_ref="ts-AAPL-BUY-1",
        )

        app.place_order(42, request)
        app.cancel_order(42)
        app.request_open_orders()
        app.request_positions()
        app.cancel_positions()
        app.request_account_summary(7, "All", "NetLiquidation")
        app.cancel_account_summary(7)
        callbacks.begin_quote(8, "MSFT")
        app.request_market_data(8, "MSFT")
        app.cancel_market_data(8)
        app.openOrder(
            42,
            SimpleNamespace(symbol="AAPL"),
            SimpleNamespace(action="BUY", totalQuantity=10.0, lmtPrice=150.0, orderRef="ts-AAPL-BUY-1"),
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
        app.tickPrice(8, 1, 149.0, SimpleNamespace())
        app.tickPrice(8, 2, 150.0, SimpleNamespace())
        app.tickPrice(8, 4, 149.5, SimpleNamespace())
        app.tickSnapshotEnd(8)
        app.managedAccounts("DU1234567,DU7654321")

        assert callbacks.managed_accounts() == ["DU1234567", "DU7654321"]

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
        assert native_order.orderRef == "ts-AAPL-BUY-1"
        assert app.cancelled[0] == 42
        assert isinstance(app.cancelled[1], FakeOrderCancel)
        assert app.open_orders_requested is True
        assert app.positions_requested is True
        assert app.positions_cancelled is True
        assert app.account_summary_requested == (7, "All", "NetLiquidation")
        assert app.account_summary_cancelled == 7
        quote_request_id, quote_contract, generic_ticks, snapshot, regulatory, options = app.market_data_requested
        assert quote_request_id == 8
        assert (
            quote_contract.symbol,
            quote_contract.secType,
            quote_contract.exchange,
            quote_contract.currency,
        ) == ("MSFT", "STK", "SMART", "USD")
        assert (generic_ticks, snapshot, regulatory, options) == ("", True, False, [])
        assert app.market_data_cancelled == 8
        trade = callbacks.trades()[0]
        assert trade.status == "Filled"
        # Placed with orderRef, echoed back on openOrder: the round trip that lets
        # reconciliation recognize an order whose confirmation never landed.
        assert trade.order_ref == "ts-AAPL-BUY-1"
        assert trade.fills[0].commission == 1.25
        assert callbacks.positions() == [IbkrPosition(symbol="AAPL", quantity=3.0)]
        assert callbacks.account_values() == [IbkrAccountValue(tag="NetLiquidation", value="1000", currency="USD")]
        assert callbacks.quote(8) == IbkrQuote(
            symbol="MSFT",
            bid=149.0,
            ask=150.0,
            last=149.5,
        )

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

    def test_quotes_return_live_and_delayed_ticks_in_request_order(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=1)
            app.quotes_to_emit = {
                "AAPL": [(1, 149.0), (2, 150.0), (4, 149.5)],
                "MSFT": [(66, 499.0), (67, 500.0), (68, 499.5)],
            }
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        quotes = client.quotes(["MSFT", "AAPL"])

        assert quotes == [
            IbkrQuote(symbol="MSFT", bid=499.0, ask=500.0, last=499.5),
            IbkrQuote(symbol="AAPL", bid=149.0, ask=150.0, last=149.5),
        ]
        assert app_holder["app"].market_data_cancellations == [1, 2]
        client.disconnect()

    def test_quote_snapshot_missing_field_is_nan(self):
        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=1)
            app.quotes_to_emit = {"AAPL": [(1, -1.0), (4, 149.5)]}
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        quote = client.quotes(["AAPL"])[0]

        assert quote.last == 149.5
        assert quote.bid != quote.bid
        assert quote.ask != quote.ask
        client.disconnect()

    def test_quote_error_wakes_request_and_cancels_market_data(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(callbacks, ready_order_id=1)
            app.quote_error = (354, "Requested market data is not subscribed")
            app_holder["app"] = app
            return app

        client = IbApiClient(app_factory=app_factory)
        client.connect("127.0.0.1", 7497, client_id=1)

        with pytest.raises(RuntimeError, match="354"):
            client.quotes(["AAPL"])

        assert app_holder["app"].market_data_cancellations == [1]
        client.disconnect()

    def test_quote_timeout_cancels_market_data(self):
        app_holder = {}

        def app_factory(callbacks):
            app = _FakeNativeApp(
                callbacks,
                ready_order_id=1,
                complete_quotes=False,
            )
            app_holder["app"] = app
            return app

        client = IbApiClient(
            app_factory=app_factory,
            request_timeout_seconds=0.01,
        )
        client.connect("127.0.0.1", 7497, client_id=1)

        with pytest.raises(TimeoutError, match="AAPL"):
            client.quotes(["AAPL"])

        assert app_holder["app"].market_data_cancellations == [1]
        client.disconnect()

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
        complete_quotes=True,
        request_error=None,
    ):
        self.callbacks = callbacks
        self.ready_order_id = ready_order_id
        self.run_error = run_error
        self.complete_open_orders = complete_open_orders
        self.complete_positions = complete_positions
        self.complete_account_summary = complete_account_summary
        self.complete_quotes = complete_quotes
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
        self.market_data_requests = []
        self.market_data_cancellations = []
        self.quotes_to_emit = {}
        self.quote_error = None
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

    def request_market_data(self, request_id, symbol):
        self.market_data_requests.append((request_id, symbol))
        if self.quote_error is not None:
            code, message = self.quote_error
            self.callbacks.record_error(request_id, code, message, None)
            return
        for tick_type, price in self.quotes_to_emit.get(symbol, []):
            self.callbacks.record_tick_price(request_id, tick_type, price)
        if self.complete_quotes:
            self.callbacks.finish_quote(request_id)

    def cancel_market_data(self, request_id):
        self.market_data_cancellations.append(request_id)


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
            account = _make_account(broker_type="interactive_brokers_socket", live_trading_enabled=flag)
            with pytest.raises(LiveTradingNotEnabledError):
                get_broker_for_account(account)
