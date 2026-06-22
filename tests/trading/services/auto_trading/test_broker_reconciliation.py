import sqlite3
from unittest.mock import Mock

from src.infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from src.infrastructure.database.db_init import init_schema
from trading.models.broker_order import BrokerOrder, OrderFill, OrderStatus
import trading.services.auto_trading.runtime as runtime_service
from tests.support.brokers import make_broker_account


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _insert_account_row(conn, account_id: int = 1, name: str = "acct-sample") -> None:
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
        "VALUES (?, 'AAPL', 'buy', 10, 150.0, ?, 'submitted', '2024-01-01T00:00:00', '2024-01-01T00:00:00')",
        (account_id, broker_order_id),
    )
    conn.commit()


def _insert_sleeve_for_account(conn, *, account_id: int = 1, sleeve_id: int = 11) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO strategy_sleeves (
            id, account_id, name, status, base_ccy, start_equity, current_cash, current_equity, created_at, updated_at
        )
        VALUES (?, ?, ?, 'active', 'USD', 10000.0, 10000.0, 10000.0, '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """,
        (sleeve_id, account_id, f"sleeve_{sleeve_id}"),
    )
    conn.commit()
    return sleeve_id


def _insert_sleeve_order_for_broker_order(
    conn,
    *,
    account_id: int = 1,
    sleeve_id: int = 11,
    broker_order_id: str,
    side: str = "buy",
    qty: float = 10.0,
    requested_price: float = 150.0,
) -> None:
    conn.execute(
        """
        INSERT INTO sleeve_orders (
            account_id, sleeve_id, strategy_name, param_set_id, rotation_decision_id,
            broker_order_id, symbol, side, qty, order_type, time_in_force,
            requested_price, status, config_version, submitted_at, updated_at
        )
        VALUES (
            ?, ?, 'trend', NULL, NULL, ?, 'AAPL', ?, ?, 'market', 'day', ?,
            'submitted', NULL, '2024-01-01T00:00:00', '2024-01-01T00:00:00'
        )
        """,
        (account_id, sleeve_id, broker_order_id, side, qty, requested_price),
    )
    conn.commit()


class TestReconcileOpenBrokerOrders:
    def test_non_ib_broker_returns_zero(self, monkeypatch) -> None:
        conn = _make_db()
        account = make_broker_account(broker_type="paper")
        mock_factory = Mock(return_value=PaperBrokerAdapter())

        result = runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=mock_factory
        )

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
        monkeypatch.setattr(runtime_service, "record_trade", lambda _conn, **kw: recorded.append(kw))

        count = runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=1.0, broker_factory=Mock(return_value=_FakeBroker())
        )

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

        fake_broker = _FakeBroker()
        runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=Mock(return_value=fake_broker)
        )
        runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=Mock(return_value=fake_broker)
        )

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

        result = runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=Mock(return_value=fake_broker)
        )

        assert result == 0
        assert _FakeBroker._disconnect_calls == 1

    def test_sleeve_partial_fill_reconciliation_is_idempotent(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _insert_open_broker_order(conn, broker_order_id="s-partial")
        sleeve_id = _insert_sleeve_for_account(conn, account_id=1, sleeve_id=101)
        _insert_sleeve_order_for_broker_order(
            conn,
            account_id=1,
            sleeve_id=sleeve_id,
            broker_order_id="s-partial",
            side="buy",
            qty=10.0,
            requested_price=150.0,
        )
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        fill = OrderFill(
            filled_qty=5.0,
            fill_price=151.0,
            fill_time="2024-01-02T10:00:00",
            commission=0.0,
            exec_id="exec-partial-001",
        )
        partial_order = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            broker_order_id="s-partial",
            status=OrderStatus.PARTIALLY_FILLED,
            filled_qty=5.0,
            avg_fill_price=151.0,
            commission=0.0,
            fills=[fill],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [partial_order]

            def disconnect(self):
                pass

        fake_broker = _FakeBroker()
        first = runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=Mock(return_value=fake_broker)
        )
        second = runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=Mock(return_value=fake_broker)
        )

        assert first == 0
        assert second == 0
        order_fills = conn.execute("SELECT COUNT(*) FROM order_fills WHERE exec_id = 'exec-partial-001'").fetchone()[0]
        sleeve_fills = conn.execute("SELECT COUNT(*) FROM sleeve_fills WHERE exec_id = 'exec-partial-001'").fetchone()[
            0
        ]
        assert order_fills == 1
        assert sleeve_fills == 1

        sleeve_order = conn.execute("SELECT status FROM sleeve_orders WHERE broker_order_id = 's-partial'").fetchone()
        assert sleeve_order is not None
        assert sleeve_order["status"] == "partially_filled"

        trade_count = conn.execute("SELECT COUNT(*) FROM trades WHERE account_id = 1").fetchone()[0]
        assert trade_count == 0

    def test_sleeve_order_status_updates_for_cancelled_and_rejected(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _insert_open_broker_order(conn, broker_order_id="s-cancel")
        _insert_open_broker_order(conn, broker_order_id="s-reject")
        sleeve_id = _insert_sleeve_for_account(conn, account_id=1, sleeve_id=102)
        _insert_sleeve_order_for_broker_order(
            conn,
            account_id=1,
            sleeve_id=sleeve_id,
            broker_order_id="s-cancel",
        )
        _insert_sleeve_order_for_broker_order(
            conn,
            account_id=1,
            sleeve_id=sleeve_id,
            broker_order_id="s-reject",
        )
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        cancelled_order = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            broker_order_id="s-cancel",
            status=OrderStatus.CANCELLED,
            filled_qty=0.0,
            avg_fill_price=None,
            commission=0.0,
            fills=[],
        )
        rejected_order = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            broker_order_id="s-reject",
            status=OrderStatus.REJECTED,
            filled_qty=0.0,
            avg_fill_price=None,
            commission=0.0,
            fills=[],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [cancelled_order, rejected_order]

            def disconnect(self):
                pass

        count = runtime_service.reconcile_open_broker_orders(
            conn, "acct-sample", account, fee=0.0, broker_factory=Mock(return_value=_FakeBroker())
        )
        assert count == 0

        statuses = conn.execute(
            """
            SELECT broker_order_id, status
            FROM sleeve_orders
            WHERE broker_order_id IN ('s-cancel', 's-reject')
            ORDER BY broker_order_id ASC
            """
        ).fetchall()
        assert [row["status"] for row in statuses] == ["cancelled", "rejected"]

        sleeve_fill_count = conn.execute("SELECT COUNT(*) FROM sleeve_fills").fetchone()[0]
        trade_count = conn.execute("SELECT COUNT(*) FROM trades WHERE account_id = 1").fetchone()[0]
        assert sleeve_fill_count == 0
        assert trade_count == 0
