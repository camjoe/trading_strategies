from unittest.mock import MagicMock, patch

import httpx
import pytest

import infrastructure.brokers.ibkr_web.adapter as ib_web_adapter_module
from infrastructure.brokers.ibkr_web import (
    IbWebApiContract,
    IbWebApiSettings,
    IbWebOrderStatusUnavailableError,
    InteractiveBrokersWebClient,
)
from infrastructure.brokers.ibkr_web.adapter import (
    InteractiveBrokersWebAdapter,
    _coerce_bool_flag,
    _coerce_number,
    _normalize_fill_time,
    _requires_manual_order_time,
    _select_ledger_row,
    _summary_amount,
)
from tests.support.brokers import make_order_request
from trading.models.orders import OrderStatus, OrderType


class TestInteractiveBrokersWebAdapter:
    def _make_client(self) -> MagicMock:
        client = MagicMock()
        client.is_connected.return_value = True
        return client

    def test_connect_delegates_to_client(self):
        client = self._make_client()
        adapter = InteractiveBrokersWebAdapter(client=client)

        adapter.connect()

        client.connect.assert_called_once_with()

    def test_place_order_submits_web_order(self):
        client = self._make_client()
        client.account_id = "U1234567"
        client.resolve_contract.return_value = IbWebApiContract(
            conid="265598",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client.fetch_trade_accounts.return_value = {"acctProps": {"U1234567": {"allowCustomerTime": False}}}
        client.submit_order.return_value = {"order_id": "123", "order_status": "Submitted"}
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.place_order(make_order_request(order_type=OrderType.MARKET))

        assert result.broker_order_id == "123"
        assert result.status == OrderStatus.SUBMITTED
        client.submit_order.assert_called_once()
        submitted_payload = client.submit_order.call_args.args[0]
        assert submitted_payload["acctId"] == "U1234567"
        assert submitted_payload["conid"] == 265598
        assert submitted_payload["secType"] == "265598:STK"
        assert submitted_payload["listingExchange"] == "NASDAQ"
        assert submitted_payload["ticker"] == "AAPL"
        assert submitted_payload["orderType"] == "MKT"
        assert submitted_payload["side"] == "BUY"
        assert submitted_payload["quantity"] == 10.0
        assert "cOID" in submitted_payload
        assert "manualOrderTime" not in submitted_payload

    @pytest.mark.parametrize(
        ("qty", "expected_exchange"),
        [(10.0, "NASDAQ"), (1.0, "NASDAQ"), (0.9342, "SMART"), (10.5, "SMART")],
    )
    def test_place_order_routes_fractional_sizes_through_smart(self, qty, expected_exchange):
        client = self._make_client()
        client.account_id = "U1234567"
        client.resolve_contract.return_value = IbWebApiContract(
            conid="272093",
            ticker="MSFT",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client.fetch_trade_accounts.return_value = {"acctProps": {}}
        client.submit_order.return_value = {"order_id": "123", "order_status": "Submitted"}
        adapter = InteractiveBrokersWebAdapter(client=client)

        adapter.place_order(make_order_request(order_type=OrderType.MARKET, qty=qty))

        assert client.submit_order.call_args.args[0]["listingExchange"] == expected_exchange

    def test_get_order_maps_a_filled_status_reply(self):
        client = self._make_client()
        # Shape of a real IBKR paper reply for a filled fractional market order.
        client.fetch_order_status.return_value = {
            "order_id": 32999660,
            "symbol": "MSFT",
            "side": "B",
            "total_size": "0.9343",
            "cum_fill": "0.9343",
            "order_type": "MARKET",
            "limit_price": "",
            "order_status": "Filled",
            "order_status_description": "Order Filled",
            "average_price": "535.92999995",
            "order_time": "261009193651",
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        order = adapter.get_order("32999660")

        client.fetch_order_status.assert_called_once_with("32999660")
        assert order is not None
        assert order.broker_order_id == "32999660"
        assert order.ticker == "MSFT"
        assert order.side == "buy"
        assert order.qty == 0.9343
        assert order.filled_qty == 0.9343
        assert order.avg_fill_price == 535.92999995
        assert order.status == OrderStatus.FILLED
        assert order.updated_at == "2026-10-09T19:36:51Z"
        assert order.fills == []
        assert order.status_reason is None

    def test_get_order_reports_a_partial_fill(self):
        client = self._make_client()
        client.fetch_order_status.return_value = {
            "symbol": "AAPL",
            "side": "S",
            "total_size": "10",
            "cum_fill": "4",
            "order_status": "Submitted",
            "average_price": "150.5",
            "order_time": "261009193651",
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        order = adapter.get_order("7")

        assert order is not None
        assert order.side == "sell"
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_qty == 4.0

    def test_get_order_carries_the_reason_for_a_terminal_non_fill(self):
        client = self._make_client()
        client.fetch_order_status.return_value = {
            "symbol": "AAPL",
            "side": "B",
            "total_size": "10",
            "cum_fill": "0.0",
            "order_status": "Cancelled",
            "order_status_description": " Order Cancelled ",
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        order = adapter.get_order("7")

        assert order is not None
        assert order.status == OrderStatus.CANCELLED
        assert order.status_reason == "Order Cancelled"
        assert order.avg_fill_price is None
        assert order.updated_at is None

    def test_get_order_is_none_when_ibkr_no_longer_has_the_order(self):
        client = self._make_client()
        client.fetch_order_status.side_effect = IbWebOrderStatusUnavailableError("gone")
        adapter = InteractiveBrokersWebAdapter(client=client)

        assert adapter.get_order("7") is None

    @pytest.mark.parametrize("payload", [{}, {"symbol": "AAPL"}, {"order_status": "Filled"}])
    def test_get_order_is_none_for_a_reply_without_a_status_and_symbol(self, payload):
        client = self._make_client()
        client.fetch_order_status.return_value = payload
        adapter = InteractiveBrokersWebAdapter(client=client)

        assert adapter.get_order("7") is None

    def test_place_order_includes_manual_order_time_when_required(self):
        client = self._make_client()
        client.account_id = "U1234567"
        client.resolve_contract.return_value = IbWebApiContract(
            conid="265598",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client.fetch_trade_accounts.return_value = {"acctProps": {"U1234567": {"allowCustomerTime": True}}}
        client.submit_order.return_value = {"order_id": "123", "order_status": "Submitted"}
        adapter = InteractiveBrokersWebAdapter(client=client)

        adapter.place_order(make_order_request(order_type=OrderType.LIMIT, price=150.0))

        submitted_payload = client.submit_order.call_args.args[0]
        assert submitted_payload["price"] == 150.0
        assert isinstance(submitted_payload["manualOrderTime"], int)

    def test_place_order_fetches_documented_rejection_description(self):
        client = self._make_client()
        client.account_id = "U1234567"
        client.resolve_contract.return_value = IbWebApiContract(
            conid="265598",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client.fetch_trade_accounts.return_value = {}
        client.submit_order.return_value = {"order_id": "123", "order_status": "Inactive"}
        client.fetch_order_status.return_value = {
            "order_status": "Inactive",
            "order_status_description": "Order rejected: insufficient buying power",
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.place_order(make_order_request())

        assert result.status == OrderStatus.REJECTED
        assert result.status_reason == "Order rejected: insufficient buying power"
        client.fetch_order_status.assert_called_once_with("123")

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

    def test_get_open_trades_reports_cumulative_state_without_a_fabricated_fill(self):
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
        assert result[0].filled_qty == 10.0
        assert result[0].avg_fill_price == 151.25
        assert result[0].updated_at == "2023-12-11T18:00:49Z"
        assert result[0].fills == []

    def test_disconnect_and_cancel_order_delegate_to_client(self):
        client = self._make_client()
        adapter = InteractiveBrokersWebAdapter(client=client)

        adapter.disconnect()
        adapter.cancel_order("123")

        client.disconnect.assert_called_once_with()
        client.cancel_order.assert_called_once_with("123")

    def test_cancel_order_requires_connection(self):
        client = self._make_client()
        client.is_connected.return_value = False
        adapter = InteractiveBrokersWebAdapter(client=client)

        with pytest.raises(RuntimeError, match="not connected"):
            adapter.cancel_order("123")

    def test_get_open_trades_skips_incomplete_rows_and_marks_partial_fill(self):
        client = self._make_client()
        client.fetch_orders.return_value = [
            {"ticker": "AAPL"},
            {"orderId": 1},
            {
                "order_id": "77",
                "description1": "MSFT",
                "side": "SELL",
                "quantity": "10",
                "filledQuantity": "5",
                "avgPrice": "101.5",
                "order_status": "Submitted",
                "limitPrice": "102.0",
                "commission": "1.25",
                "lastExecutionTime_r": "2024-01-02T03:04:05Z",
            },
        ]
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_open_trades()

        assert len(result) == 1
        trade = result[0]
        assert trade.ticker == "MSFT"
        assert trade.side == "sell"
        assert trade.status == OrderStatus.PARTIALLY_FILLED
        assert trade.price == 102.0
        assert trade.commission == 1.25
        assert trade.filled_qty == 5.0
        assert trade.avg_fill_price == 101.5
        assert trade.updated_at == "2024-01-02T03:04:05Z"
        assert trade.fills == []

    def test_get_open_trades_reports_a_missing_average_price_as_none(self):
        client = self._make_client()
        client.fetch_orders.return_value = [
            {
                "order_id": "77",
                "description1": "MSFT",
                "side": "SELL",
                "quantity": "10",
                "filledQuantity": "5",
                "order_status": "Submitted",
                "limitPrice": "102.0",
            },
        ]
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_open_trades()

        assert len(result) == 1
        assert result[0].status == OrderStatus.PARTIALLY_FILLED
        assert result[0].avg_fill_price is None

    def test_get_open_trades_fetches_documented_cancellation_description(self):
        client = self._make_client()
        client.fetch_orders.return_value = [
            {
                "order_id": "77",
                "ticker": "MSFT",
                "side": "SELL",
                "quantity": "10",
                "order_status": "Cancelled",
            },
        ]
        client.fetch_order_status.return_value = {
            "order_status": "Cancelled",
            "order_status_description": "Order cancelled by exchange",
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_open_trades()

        assert result[0].status == OrderStatus.CANCELLED
        assert result[0].status_reason == "Order cancelled by exchange"
        client.fetch_order_status.assert_called_once_with("77")

    def test_get_open_trades_keeps_terminal_status_when_description_is_unavailable(self):
        client = self._make_client()
        client.fetch_orders.return_value = [
            {
                "order_id": "77",
                "ticker": "MSFT",
                "side": "SELL",
                "quantity": "10",
                "order_status": "Cancelled",
            },
        ]
        client.fetch_order_status.side_effect = IbWebOrderStatusUnavailableError("503 order no longer cached")
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_open_trades()

        assert result[0].status == OrderStatus.CANCELLED
        assert result[0].status_reason is None

    def test_get_open_trades_does_not_fetch_description_for_active_order(self):
        client = self._make_client()
        client.fetch_orders.return_value = [
            {
                "order_id": "77",
                "ticker": "MSFT",
                "side": "SELL",
                "quantity": "10",
                "order_status": "Submitted",
            },
        ]
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.get_open_trades()

        assert result[0].status == OrderStatus.SUBMITTED
        assert result[0].status_reason is None
        client.fetch_order_status.assert_not_called()

    def test_get_positions_skips_blank_symbols_and_unparseable_quantities(self):
        client = self._make_client()
        client.fetch_positions.return_value = [
            {"description": "  ", "position": "1"},
            {"contractDesc": "AAPL", "position": "5"},
            {"ticker": "MSFT", "position": " "},
        ]
        adapter = InteractiveBrokersWebAdapter(client=client)

        assert adapter.get_positions() == {"AAPL": 5.0}

    def test_get_account_info_uses_fallback_ledger_and_summary_values(self):
        client = self._make_client()
        client.fetch_ledger.return_value = {
            "EUR": {
                "cashbalance": "1234.5",
                "stockmarketvalue": "50",
                "netliquidationvalue": "1500",
            }
        }
        client.fetch_summary.return_value = {
            "buyingpower": "skip",
            "availablefunds": {"value": "2222.0"},
        }
        adapter = InteractiveBrokersWebAdapter(client=client)

        assert adapter.get_account_info() == {
            "TotalCashValue": 1234.5,
            "BuyingPower": 2222.0,
            "GrossPositionValue": 50.0,
            "NetLiquidation": 1500.0,
        }

    def test_get_quotes_skips_rows_for_unknown_conids(self):
        client = self._make_client()
        client.resolve_conid.return_value = "265598"
        client.fetch_marketdata_snapshot.return_value = [{"conid": "999", "31": "1"}]
        adapter = InteractiveBrokersWebAdapter(client=client)

        assert adapter.get_quotes(["AAPL"]) == {}


class TestIbWebAdapterHelpers:
    def test_normalize_fill_time_uses_current_time_for_missing_values(self):
        with patch.object(ib_web_adapter_module, "utc_now_iso", return_value="2024-01-01T00:00:00Z"):
            assert _normalize_fill_time(None) == "2024-01-01T00:00:00Z"
            assert _normalize_fill_time("   ") == "2024-01-01T00:00:00Z"

    def test_select_ledger_row_returns_first_available_mapping_or_empty_dict(self):
        assert _select_ledger_row({"EUR": {"cashbalance": 1}}) == {"cashbalance": 1}
        assert _select_ledger_row({"EUR": "skip", "JPY": []}) == {}

    def test_summary_amount_returns_none_for_non_mapping_entry(self):
        assert _summary_amount({"buyingpower": "bad"}, "buyingpower") is None

    def test_requires_manual_order_time_handles_missing_account_properties(self):
        assert _requires_manual_order_time({}, "U1") is False
        assert _requires_manual_order_time({"acctProps": {"U1": "bad"}}, "U1") is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(" ", None), ("1,234.5", 1234.5)],
    )
    def test_coerce_number_handles_blank_and_numeric_strings(self, value, expected):
        assert _coerce_number(value) == expected

    @pytest.mark.parametrize(("value", "expected"), [("maybe", False), ("true", True), (None, False)])
    def test_coerce_bool_flag_handles_invalid_values(self, value, expected):
        assert _coerce_bool_flag(value) is expected


class TestGetOrderThroughTheClient:
    """The adapter's lookup, wired to the real client over a fake gateway."""

    def _adapter(self, status_response: httpx.Response) -> InteractiveBrokersWebAdapter:
        def handler(request: httpx.Request) -> httpx.Response:
            routes = {
                "/iserver/auth/status": httpx.Response(200, json={"authenticated": True, "connected": True}),
                "/portfolio/accounts": httpx.Response(200, json=[{"accountId": "DU1234567"}]),
                "/iserver/accounts": httpx.Response(200, json={"accounts": ["DU1234567"]}),
                "/iserver/account/order/status/32999660": status_response,
            }
            return routes[request.url.path]

        client = InteractiveBrokersWebClient(
            settings=IbWebApiSettings(
                base_url="https://example.test",
                account_id="DU1234567",
                headers={},
                keepalive_enabled=False,
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test"),
        )
        adapter = InteractiveBrokersWebAdapter(client=client)
        adapter.connect()
        return adapter

    def test_a_filled_reply_becomes_a_filled_broker_order(self):
        adapter = self._adapter(
            httpx.Response(
                200,
                json={
                    "symbol": "MSFT",
                    "side": "B",
                    "total_size": "0.9343",
                    "cum_fill": "0.9343",
                    "order_status": "Filled",
                    "average_price": "535.92999995",
                    "order_time": "261009193651",
                },
            )
        )

        order = adapter.get_order("32999660")

        assert order is not None
        assert (order.ticker, order.side, order.status) == ("MSFT", "buy", OrderStatus.FILLED)
        assert order.filled_qty == 0.9343

    def test_a_status_cache_miss_is_none(self):
        adapter = self._adapter(httpx.Response(503, text="order status unavailable"))

        assert adapter.get_order("32999660") is None

    def test_any_other_failure_reaches_the_caller(self):
        adapter = self._adapter(httpx.Response(500, text="boom"))

        with pytest.raises(RuntimeError, match="500"):
            adapter.get_order("32999660")
