import sqlite3
from unittest.mock import Mock

from trading.brokers.paper_adapter import PaperBrokerAdapter
from trading.database.db_init import init_schema
from trading.models.broker_order import BrokerOrder, OrderFill, OrderStatus
import trading.services.auto_trading.runtime as runtime_service
from tests.support.brokers import make_broker_account


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


class TestReconcileOpenBrokerOrders:
    def test_non_ib_broker_returns_zero(self, monkeypatch) -> None:
        conn = _make_db()
        account = make_broker_account(broker_type="paper")
        mock_factory = Mock(return_value=PaperBrokerAdapter())
        monkeypatch.setattr(runtime_service, "get_broker_for_account", mock_factory)

        result = runtime_service.reconcile_open_broker_orders(conn, "test-account", account, fee=0.0)

        assert result == 0
        mock_factory.assert_called_once_with(account)

    def test_newly_filled_order_increments_count(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _insert_open_broker_order(conn, broker_order_id="42")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        fill = OrderFill(
            filled_qty=10.0,
            fill_price=151.0,
            fill_time="2024-01-02T10:00:00",
            commission=0.5,
            exec_id="exec-001",
        )
        filled_order = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            broker_order_id="42",
            status=OrderStatus.FILLED,
            filled_qty=10.0,
            avg_fill_price=151.0,
            commission=0.5,
            fills=[fill],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [filled_order]

            def disconnect(self):
                pass

        recorded: list[dict[str, object]] = []
        monkeypatch.setattr(runtime_service, "get_broker_for_account", Mock(return_value=_FakeBroker()))
        monkeypatch.setattr(runtime_service, "record_trade", lambda _conn, **kw: recorded.append(kw))

        count = runtime_service.reconcile_open_broker_orders(conn, "test-account", account, fee=1.0)

        assert count == 1
        assert len(recorded) == 1
        assert recorded[0]["ticker"] == "AAPL"
        assert recorded[0]["price"] == 151.0

    def test_duplicate_fill_is_idempotent(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _insert_open_broker_order(conn, broker_order_id="99")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        fill = OrderFill(
            filled_qty=10.0,
            fill_price=152.0,
            fill_time="2024-01-02T10:00:00",
            commission=0.0,
            exec_id="exec-dup",
        )
        partial_order = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            broker_order_id="99",
            status=OrderStatus.SUBMITTED,
            filled_qty=5.0,
            avg_fill_price=152.0,
            commission=0.0,
            fills=[fill],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [partial_order]

            def disconnect(self):
                pass

        monkeypatch.setattr(runtime_service, "get_broker_for_account", Mock(return_value=_FakeBroker()))

        runtime_service.reconcile_open_broker_orders(conn, "test-account", account, fee=0.0)
        runtime_service.reconcile_open_broker_orders(conn, "test-account", account, fee=0.0)

        fills_count = conn.execute("SELECT COUNT(*) FROM order_fills WHERE exec_id = 'exec-dup'").fetchone()[0]
        assert fills_count == 1

    def test_disconnect_called_even_when_no_open_orders(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        class _FakeBroker:
            _disconnect_calls = 0

            def get_open_trades(self):
                return []

            def disconnect(self):
                _FakeBroker._disconnect_calls += 1

        fake_broker = _FakeBroker()
        monkeypatch.setattr(runtime_service, "get_broker_for_account", Mock(return_value=fake_broker))

        result = runtime_service.reconcile_open_broker_orders(conn, "test-account", account, fee=0.0)

        assert result == 0
        assert _FakeBroker._disconnect_calls == 1
