from unittest.mock import Mock

from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.books import ensure_default_book_id
from tests.support.brokers import make_broker_account
from tests.support.db_schema import memory_db_at_head
from trading.models.orders import ORDER_STATUS_PENDING, BrokerOrder, OrderFill, OrderInsert, OrderStatus
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.open_order_reconciliation import reconcile_open_orders


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
    book_id = ensure_default_book_id(conn, account_id)
    order_id = OrderRepository(conn).insert(
        OrderInsert(
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
    )
    return book_id, order_id


def _pending_clean_order(
    conn,
    *,
    client_order_id: str,
    account_id: int = 1,
    symbol: str = "AAPL",
    side: str = "buy",
    qty: float = 10.0,
    price: float = 150.0,
) -> tuple[int, int]:
    """Seed the row a crashed send leaves behind: pending, with no broker order id."""
    book_id = ensure_default_book_id(conn, account_id)
    order_id = OrderRepository(conn).insert(
        OrderInsert(
            book_id=book_id,
            account_id=account_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            requested_price=price,
            status=ORDER_STATUS_PENDING,
            submitted_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
    )
    return book_id, order_id


class TestAdoptPendingOrders:
    """The recovery path: an order the broker took whose confirmation never landed."""

    def test_pending_row_is_adopted_and_filled_from_the_brokers_echoed_client_id(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _pending_clean_order(conn, client_order_id="ts-AAPL-BUY-1")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        live = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            client_order_id="ts-AAPL-BUY-1",
            broker_order_id="77",
            status=OrderStatus.FILLED,
            filled_qty=10.0,
            avg_fill_price=150.5,
            commission=0.25,
            fills=[
                OrderFill(
                    filled_qty=10.0,
                    fill_price=150.5,
                    fill_time="2024-01-02T10:00:00",
                    commission=0.25,
                    exec_id="exec-adopt",
                )
            ],
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [live]

            def disconnect(self):
                pass

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))

        assert outcome.adopted_pending == 1
        assert outcome.unresolved_pending_client_order_ids == []
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None
        # The row now carries the broker's id, and the fill reached the book.
        assert order.broker_order_id == "77"
        assert order.status == "filled"
        assert order.submitted_at == "2024-01-01T00:00:00"  # the send time, not the poll's
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 10.0

    def test_pending_row_no_live_order_claims_is_reported_not_resolved(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _pending_clean_order(conn, client_order_id="ts-AAPL-BUY-2")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        class _EmptyBroker:
            def get_open_trades(self):
                return []

            def disconnect(self):
                pass

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_EmptyBroker()))

        assert outcome.adopted_pending == 0
        assert outcome.unresolved_pending_client_order_ids == ["ts-AAPL-BUY-2"]
        # Untouched: it may have been rejected on the way in, or filled and aged off
        # the broker's list. Guessing either way would misstate the book.
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None
        assert order.status == ORDER_STATUS_PENDING
        assert order.broker_order_id is None

    def test_a_different_accounts_client_id_is_not_adopted(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _pending_clean_order(conn, client_order_id="ts-AAPL-BUY-3")

        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        stranger = BrokerOrder(
            account_id=1,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            client_order_id="someone-elses-order",
            broker_order_id="88",
            status=OrderStatus.FILLED,
        )

        class _FakeBroker:
            def get_open_trades(self):
                return [stranger]

            def disconnect(self):
                pass

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))

        assert outcome.adopted_pending == 0
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None
        assert order.status == ORDER_STATUS_PENDING


class TestReconcileOpenBrokerOrders:
    def test_non_ib_broker_returns_zero(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        account = make_broker_account(broker_type="paper")
        mock_factory = Mock(return_value=PaperBrokerAdapter())

        result = reconcile_open_orders(conn, account, broker_factory=mock_factory)

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

        count = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))

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
        first = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=fake_broker))
        second = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=fake_broker))

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

        result = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))

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

        count = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))
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

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))

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

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_FakeBroker()))

        assert outcome.unreported_broker_order_ids == []
        assert outcome.has_unreported is False
