from unittest.mock import Mock

import trading.services.auto_trading.runtime as runtime_service
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.brokers import make_broker_account
from tests.support.db_schema import memory_db_at_head
from trading.models.orders.broker_order import BrokerOrder, OrderFill, OrderStatus
from trading.repositories.book_bridge import default_book_id
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository


def _make_db():
    return memory_db_at_head()


def _insert_account_row(conn, account_id: int = 1, name: str = "acct-sample") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO accounts (id, name, initial_cash, created_at, updated_at) "
        "VALUES (?, ?, 10000, '2024-01-01T00:00:00', '2024-01-01T00:00:00')",
        (account_id, name),
    )
    conn.commit()


def _open_clean_order(
    conn,
    *,
    broker_order_id: str,
    account_id: int = 1,
    symbol: str = "AAPL",
    side: str = "buy",
    qty: float = 10.0,
    price: float = 150.0,
) -> tuple[int, int]:
    """Seed an open clean orders row on the account's default book."""
    book_id = default_book_id(conn, account_id)
    order_id = OrderRepository(conn).insert(
        book_id=book_id,
        account_id=account_id,
        broker_order_id=broker_order_id,
        symbol=symbol,
        side=side,
        qty=qty,
        requested_price=price,
        status="submitted",
        submitted_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )
    return book_id, order_id


class TestReconcileOpenBrokerOrders:
    def test_non_ib_broker_returns_zero(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        account = make_broker_account(broker_type="paper")
        mock_factory = Mock(return_value=PaperBrokerAdapter())

        result = runtime_service.reconcile_open_broker_orders(conn, account, broker_factory=mock_factory)

        assert result.newly_filled == 0
        mock_factory.assert_called_once_with(account)

    def test_newly_filled_order_applies_book_fill_and_records_trade(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
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
            fills=[
                OrderFill(
                    filled_qty=10.0,
                    fill_price=151.0,
                    fill_time="2024-01-02T10:00:00",
                    commission=0.5,
                    exec_id="exec-001",
                )
            ],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [filled_order]

            def disconnect(self):
                pass

        count = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=_FakeBroker())
        )

        assert count.newly_filled == 1
        # The clean order + book state were updated from the async fill.
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None
        assert order.status == "filled"
        exec_ids = OrderRepository(conn).fetch_fill_exec_ids(order_id=order_id)
        assert exec_ids == {"exec-001"}
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 10.0

    def test_duplicate_fill_is_idempotent(self, monkeypatch) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="99")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        partial_order = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            broker_order_id="99",
            status=OrderStatus.PARTIALLY_FILLED,
            filled_qty=5.0,
            avg_fill_price=152.0,
            commission=0.0,
            fills=[
                OrderFill(
                    filled_qty=5.0,
                    fill_price=152.0,
                    fill_time="2024-01-02T10:00:00",
                    commission=0.0,
                    exec_id="exec-dup",
                )
            ],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [partial_order]

            def disconnect(self):
                pass

        fake_broker = _FakeBroker()
        first = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=fake_broker)
        )
        second = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=fake_broker)
        )

        # Partial fill is not FILLED → newly_filled stays 0 across both polls.
        assert first.newly_filled == 0
        assert second.newly_filled == 0
        fills_count = conn.execute("SELECT COUNT(*) FROM order_fills WHERE exec_id = 'exec-dup'").fetchone()[0]
        assert fills_count == 1
        # The book fill is applied exactly once (qty 5, not 10).
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 5.0

    def test_disconnect_called_even_when_no_open_orders(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        class _FakeBroker:
            _disconnect_calls = 0

            def get_open_trades(self):
                return []

            def disconnect(self):
                _FakeBroker._disconnect_calls += 1

        result = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=_FakeBroker())
        )

        assert result.newly_filled == 0
        assert _FakeBroker._disconnect_calls == 1

    def test_cancelled_and_rejected_update_clean_order_status(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, cancel_id = _open_clean_order(conn, broker_order_id="s-cancel")
        _, reject_id = _open_clean_order(conn, broker_order_id="s-reject")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        def _terminal_order(broker_order_id: str, status: OrderStatus) -> BrokerOrder:
            return BrokerOrder(
                account_id=1,
                ticker="AAPL",
                side="buy",
                qty=10.0,
                price=150.0,
                broker_order_id=broker_order_id,
                status=status,
                filled_qty=0.0,
                avg_fill_price=None,
                commission=0.0,
                fills=[],
            )

        class _FakeBroker:
            def get_open_trades(self):
                return [
                    _terminal_order("s-cancel", OrderStatus.CANCELLED),
                    _terminal_order("s-reject", OrderStatus.REJECTED),
                ]

            def disconnect(self):
                pass

        count = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=_FakeBroker())
        )
        assert count.newly_filled == 0

        repo = OrderRepository(conn)
        cancelled = repo.fetch_by_id(order_id=cancel_id)
        rejected = repo.fetch_by_id(order_id=reject_id)
        assert cancelled is not None and cancelled.status == "cancelled"
        assert rejected is not None and rejected.status == "rejected"

    def test_orders_the_broker_omits_are_reported_and_left_untouched(self) -> None:
        """An order the broker no longer mentions is surfaced, never guessed at.

        IBKR's order endpoint covers the current day, so a `day` order that expired
        at a prior close simply stops appearing. It might also have filled on a day
        nothing ran — marking it cancelled would corrupt the book, so the row stays
        open and the id is reported instead.
        """
        conn = _make_db()
        _insert_account_row(conn)
        _, reported_id = _open_clean_order(conn, broker_order_id="ib-reported")
        _, omitted_id = _open_clean_order(conn, broker_order_id="ib-omitted")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        class _FakeBroker:
            def get_open_trades(self):
                return [
                    BrokerOrder(
                        account_id=1,
                        ticker="AAPL",
                        side="buy",
                        qty=10.0,
                        price=150.0,
                        broker_order_id="ib-reported",
                        status=OrderStatus.SUBMITTED,
                        filled_qty=0.0,
                        avg_fill_price=None,
                        commission=0.0,
                        fills=[],
                    )
                ]

            def disconnect(self):
                pass

        outcome = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=_FakeBroker())
        )

        assert outcome.unreported_broker_order_ids == ["ib-omitted"]
        assert outcome.has_unreported is True

        repo = OrderRepository(conn)
        omitted = repo.fetch_by_id(order_id=omitted_id)
        assert omitted is not None and omitted.status == "submitted"
        reported = repo.fetch_by_id(order_id=reported_id)
        assert reported is not None and reported.status == "submitted"

    def test_no_unreported_ids_when_broker_covers_every_open_order(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _open_clean_order(conn, broker_order_id="ib-1")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        class _FakeBroker:
            def get_open_trades(self):
                return [
                    BrokerOrder(
                        account_id=1,
                        ticker="AAPL",
                        side="buy",
                        qty=10.0,
                        price=150.0,
                        broker_order_id="ib-1",
                        status=OrderStatus.SUBMITTED,
                        filled_qty=0.0,
                        avg_fill_price=None,
                        commission=0.0,
                        fills=[],
                    )
                ]

            def disconnect(self):
                pass

        outcome = runtime_service.reconcile_open_broker_orders(
            conn, account, broker_factory=Mock(return_value=_FakeBroker())
        )

        assert outcome.unreported_broker_order_ids == []
        assert outcome.has_unreported is False
