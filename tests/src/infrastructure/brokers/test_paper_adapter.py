import pytest

from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.brokers import make_order_request
from trading.models.orders import OrderFill, OrderStatus


class TestPaperBrokerAdapter:
    def test_place_order_fills_immediately(self):
        adapter = PaperBrokerAdapter()
        order = make_order_request()
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
        order = make_order_request(qty=5.0, price=200.0)
        filled = adapter.place_order(order)

        fill: OrderFill = filled.fills[0]
        assert fill.filled_qty == 5.0
        assert fill.fill_price == 200.0
        assert fill.commission == 0.0
        assert fill.fill_time is not None

    def test_place_order_sets_submitted_and_updated_at(self):
        adapter = PaperBrokerAdapter()
        filled = adapter.place_order(make_order_request())
        assert filled.submitted_at is not None
        assert filled.updated_at is not None

    def test_place_order_returns_a_new_order_and_leaves_the_request_alone(self):
        """The port's contract: an adapter answers with its own object.

        Guards the whole request/response split — an adapter that mutated and
        returned the caller's request would pass every other test here.
        """
        adapter = PaperBrokerAdapter()
        request = make_order_request()
        filled = adapter.place_order(request)

        assert filled is not request
        assert not hasattr(request, "status")
        assert (request.ticker, request.side, request.qty, request.price) == (
            filled.ticker,
            filled.side,
            filled.qty,
            filled.price,
        )

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
