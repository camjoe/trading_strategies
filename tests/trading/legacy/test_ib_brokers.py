"""Legacy socket/TWS Interactive Brokers coverage.

These tests are separated from ``test_brokers.py`` so the current/default broker
surface reads as paper + IBKR Web API, while the older socket/TWS path remains
clearly marked as legacy support.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from trading.brokers.factory import LiveTradingNotEnabledError, get_broker_for_account
from trading.brokers.legacy.ib_adapter import InteractiveBrokersAdapter, _map_ib_status
from trading.brokers.legacy.ib_client import IBClientProtocol, IbApiClient
from trading.models.broker_order import BrokerOrder, OrderStatus, OrderType
from tests.support.account_records import make_account_record


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


def _adapter_with_mock_client() -> tuple[InteractiveBrokersAdapter, MagicMock]:
    client = _mock_ib_client()
    adapter = InteractiveBrokersAdapter(client=client, host="127.0.0.1", port=7497, client_id=1)
    return adapter, client


class TestLegacyIbFactoryRouting:
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
            patch("trading.brokers.legacy.factory.IbAsyncClient", return_value=mock_client),
        ):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersAdapter)
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
        with patch("trading.brokers.legacy.factory.IbAsyncClient", return_value=mock_client):
            broker = get_broker_for_account(account)
        assert isinstance(broker, InteractiveBrokersAdapter)

    def test_ibapi_backend_uses_ib_api_client(self):
        import trading.brokers.legacy.factory as legacy_factory_module

        account = _make_account(
            broker_type="interactive_brokers",
            broker_host="127.0.0.1",
            broker_port=7497,
            broker_client_id=1,
        )
        mock_client = _mock_ib_client()
        original = legacy_factory_module.IB_CLIENT_BACKEND
        try:
            legacy_factory_module.IB_CLIENT_BACKEND = "ibapi"
            with (
                patch("trading.brokers.factory._require_live_trading_enabled"),
                patch("trading.brokers.legacy.factory.IbApiClient", return_value=mock_client),
            ):
                broker = get_broker_for_account(account)
            assert isinstance(broker, InteractiveBrokersAdapter)
        finally:
            legacy_factory_module.IB_CLIENT_BACKEND = original

    def test_unknown_ib_backend_raises_value_error(self):
        import trading.brokers.legacy.factory as legacy_factory_module

        account = _make_account(broker_type="interactive_brokers")
        original = legacy_factory_module.IB_CLIENT_BACKEND
        try:
            legacy_factory_module.IB_CLIENT_BACKEND = "not_a_real_backend"
            with patch("trading.brokers.factory._require_live_trading_enabled"):
                with pytest.raises(ValueError, match="Unknown IB_CLIENT_BACKEND"):
                    get_broker_for_account(account)
        finally:
            legacy_factory_module.IB_CLIENT_BACKEND = original


class TestLegacyInteractiveBrokersAdapter:
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

    def test_get_positions_returns_symbol_qty_dict(self):
        adapter, client = _adapter_with_mock_client()
        pos1 = SimpleNamespace(contract=SimpleNamespace(symbol="AAPL"), position=10.0)
        pos2 = SimpleNamespace(contract=SimpleNamespace(symbol="MSFT"), position=5.0)
        client.positions.return_value = [pos1, pos2]

        assert adapter.get_positions() == {"AAPL": 10.0, "MSFT": 5.0}

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


class TestLegacyIbApiClient:
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
        assert isinstance(IbApiClient(), IBClientProtocol)


class TestLegacyIbStatusMap:
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


class TestLegacyLiveTradingSafety:
    def test_ib_adapter_blocked_when_flag_is_zero(self):
        for flag in (0, "0", None, False):
            account = _make_account(broker_type="interactive_brokers", live_trading_enabled=flag)
            with pytest.raises(LiveTradingNotEnabledError):
                get_broker_for_account(account)
