from unittest.mock import MagicMock

from trading.brokers.ib_web_adapter import InteractiveBrokersWebAdapter
from trading.brokers.ib_web_client import IbWebApiContract
from trading.models.broker_order import OrderStatus, OrderType
from tests.support import make_broker_order


class TestInteractiveBrokersWebAdapter:
    def _make_client(self) -> MagicMock:
        client = MagicMock()
        client.is_connected.return_value = True
        return client

    def test_place_order_submits_web_order(self):
        client = self._make_client()
        client.account_id = "U1234567"
        client.resolve_contract.return_value = IbWebApiContract(
            conid="265598",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client.fetch_trade_accounts.return_value = {
            "acctProps": {"U1234567": {"allowCustomerTime": False}}
        }
        client.submit_order.return_value = {"order_id": "123", "order_status": "Submitted"}
        adapter = InteractiveBrokersWebAdapter(client=client)

        result = adapter.place_order(make_broker_order(order_type=OrderType.MARKET))

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

    def test_place_order_includes_manual_order_time_when_required(self):
        client = self._make_client()
        client.account_id = "U1234567"
        client.resolve_contract.return_value = IbWebApiContract(
            conid="265598",
            ticker="AAPL",
            sec_type="STK",
            listing_exchange="NASDAQ",
        )
        client.fetch_trade_accounts.return_value = {
            "acctProps": {"U1234567": {"allowCustomerTime": True}}
        }
        client.submit_order.return_value = {"order_id": "123", "order_status": "Submitted"}
        adapter = InteractiveBrokersWebAdapter(client=client)

        adapter.place_order(make_broker_order(order_type=OrderType.LIMIT, price=150.0))

        submitted_payload = client.submit_order.call_args.args[0]
        assert submitted_payload["price"] == 150.0
        assert isinstance(submitted_payload["manualOrderTime"], int)

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
