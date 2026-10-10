import logging
from decimal import Decimal
from unittest.mock import Mock

from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.books import ensure_default_book_id
from tests.support.brokers import make_broker_account
from tests.support.db_schema import memory_db_at_head
from trading.models.orders import ORDER_STATUS_PENDING, BrokerOrder, OrderFill, OrderInsert, OrderStatus
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.open_order_reconciliation import reconcile_open_orders


class _LookupBroker:
    """A broker whose open-order list is empty but which can look an order up by id.

    Like the IBKR Web API, it reports cumulative state rather than executions.
    """

    reports_executions = False

    def __init__(self, orders_by_id: dict[str, BrokerOrder]) -> None:
        self._orders_by_id = orders_by_id

    def get_open_trades(self) -> list[BrokerOrder]:
        return []

    def get_order(self, broker_order_id: str) -> BrokerOrder | None:
        return self._orders_by_id.get(broker_order_id)

    def disconnect(self) -> None:
        pass


class _ListedBroker(_LookupBroker):
    """A broker whose open-order list reports the given orders, as the Web API list does."""

    def __init__(self, listed: list[BrokerOrder]) -> None:
        super().__init__({})
        self._listed = listed

    def get_open_trades(self) -> list[BrokerOrder]:
        return self._listed


def _looked_up_order(broker_order_id: str, *, status: OrderStatus, filled_qty: float) -> BrokerOrder:
    """The cumulative state a lookup by id reports: no individual executions."""
    return BrokerOrder(
        account_id=0,
        ticker="AAPL",
        side="buy",
        qty=10.0,
        price=0.0,
        broker_order_id=broker_order_id,
        status=status,
        filled_qty=filled_qty,
        avg_fill_price=151.0 if filled_qty > 0 else None,
        updated_at="2024-01-02T10:00:00Z",
    )


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
            reports_executions = True

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
            reports_executions = True

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
            reports_executions = True

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
            reports_executions = True

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
            reports_executions = True

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
            reports_executions = True

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
            reports_executions = True

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
            reports_executions = True

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

            def get_order(self, _broker_order_id):
                return None

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
            reports_executions = True

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

    def test_an_order_the_list_omits_is_filled_from_a_lookup_by_id(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        broker = _LookupBroker({"42": _looked_up_order("42", status=OrderStatus.FILLED, filled_qty=10.0)})

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=broker))

        assert outcome.newly_filled == 1
        assert outcome.unreported_broker_order_ids == []
        repo = OrderRepository(conn)
        order = repo.fetch_by_id(order_id=order_id)
        assert order is not None
        assert order.status == "filled"
        assert order.filled_qty == 10.0
        assert repo.fetch_fill_exec_ids(order_id=order_id) == {"42:cum:10.0"}
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 10.0

    def test_polling_the_same_cumulative_fill_twice_posts_it_once(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        broker = _LookupBroker({"42": _looked_up_order("42", status=OrderStatus.PARTIALLY_FILLED, filled_qty=4.0)})

        for _ in range(2):
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=broker))

        assert OrderRepository(conn).fetch_fill_exec_ids(order_id=order_id) == {"42:cum:4.0"}
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 4.0

    def test_a_later_lookup_posts_only_the_size_filled_since(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        for status, cumulative in ((OrderStatus.PARTIALLY_FILLED, 4.0), (OrderStatus.FILLED, 10.0)):
            broker = _LookupBroker({"42": _looked_up_order("42", status=status, filled_qty=cumulative)})
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=broker))

        assert OrderRepository(conn).fetch_fill_exec_ids(order_id=order_id) == {"42:cum:4.0", "42:cum:10.0"}
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 10.0

    def test_a_lookup_that_finds_a_cancelled_order_resolves_the_row(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        cancelled = _looked_up_order("42", status=OrderStatus.CANCELLED, filled_qty=0.0)
        cancelled.status_reason = "Order Cancelled"
        broker = _LookupBroker({"42": cancelled})

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=broker))

        assert outcome.newly_filled == 0
        assert outcome.unreported_broker_order_ids == []
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None
        assert order.status == "cancelled"
        assert order.status_reason == "Order Cancelled"
        assert OrderRepository(conn).fetch_fill_exec_ids(order_id=order_id) == set()

    def test_a_failed_lookup_leaves_the_order_unreported_instead_of_failing_the_run(self, caplog) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        class _BrokenLookupBroker(_LookupBroker):
            def get_order(self, broker_order_id: str) -> BrokerOrder | None:
                raise RuntimeError("IBKR Web API request failed for GET /iserver/account/order/status/42: 500")

        with caplog.at_level(logging.WARNING, logger="trading.services.execution.open_order_reconciliation"):
            outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_BrokenLookupBroker({})))

        assert outcome.unreported_broker_order_ids == ["42"]
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None and order.status == "submitted"
        assert "Lookup of broker order 42 failed" in caplog.text

    def test_a_fill_with_no_price_is_left_unapplied_and_unreported(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        priceless = _looked_up_order("42", status=OrderStatus.FILLED, filled_qty=10.0)
        priceless.avg_fill_price = None

        outcome = reconcile_open_orders(
            conn, account, broker_factory=Mock(return_value=_LookupBroker({"42": priceless}))
        )

        assert outcome.newly_filled == 0
        assert outcome.unreported_broker_order_ids == ["42"]
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None and order.status == "submitted"
        assert PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL") is None

    def test_a_lookup_reporting_less_than_is_recorded_changes_nothing(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _open_clean_order(conn, broker_order_id="42")
        repo = OrderRepository(conn)
        repo.insert_fill(
            order_id=order_id,
            filled_qty=Decimal("6"),
            fill_price=Decimal("151"),
            fill_time="2024-01-02T10:00:00Z",
            exec_id="exec-001",
        )
        repo.update_status(
            order_id=order_id,
            status="partially_filled",
            filled_qty=Decimal("6"),
            avg_fill_price=Decimal("151"),
            updated_at="2024-01-02T10:00:00Z",
            status_reason=None,
        )
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        behind = _looked_up_order("42", status=OrderStatus.PARTIALLY_FILLED, filled_qty=4.0)

        outcome = reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_LookupBroker({"42": behind})))

        assert outcome.unreported_broker_order_ids == ["42"]
        order = repo.fetch_by_id(order_id=order_id)
        assert order is not None
        assert order.filled_qty == 6.0
        assert repo.fetch_fill_exec_ids(order_id=order_id) == {"exec-001"}

    def test_a_partial_fill_listed_across_polls_posts_each_part_once(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        for status, cumulative in ((OrderStatus.PARTIALLY_FILLED, 4.0), (OrderStatus.FILLED, 10.0)):
            broker = _ListedBroker([_looked_up_order("42", status=status, filled_qty=cumulative)])
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=broker))

        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 10.0
        assert OrderRepository(conn).fetch_fill_totals(order_id=order_id)[0] == 10

    def test_commission_is_posted_once_across_cumulative_reports(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        for status, cumulative, commission in (
            (OrderStatus.PARTIALLY_FILLED, 4.0, 1.0),
            (OrderStatus.FILLED, 10.0, 1.5),
        ):
            order = _looked_up_order("42", status=status, filled_qty=cumulative)
            order.commission = commission
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_ListedBroker([order])))

        assert OrderRepository(conn).fetch_fill_totals(order_id=order_id)[2] == Decimal("1.5")

    def test_a_cumulative_report_posts_what_the_recorded_fills_do_not_cover(self) -> None:
        """The posting basis is the fill rows, not the order's own filled_qty.

        If a crash left the order row at the cumulative size with no fill rows, the next
        poll must still post the fill rather than see "nothing new".
        """
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        OrderRepository(conn).update_status(
            order_id=order_id,
            status="partially_filled",
            filled_qty=Decimal("4"),
            avg_fill_price=Decimal("151"),
            updated_at="2024-01-02T10:00:00Z",
        )
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        broker = _ListedBroker([_looked_up_order("42", status=OrderStatus.PARTIALLY_FILLED, filled_qty=4.0)])

        reconcile_open_orders(conn, account, broker_factory=Mock(return_value=broker))

        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 4.0

    def test_a_later_part_of_a_fill_is_priced_at_what_that_part_cost(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        for status, cumulative, average in (
            (OrderStatus.PARTIALLY_FILLED, 5.0, 100.0),
            (OrderStatus.FILLED, 10.0, 105.0),
        ):
            order = _looked_up_order("42", status=status, filled_qty=cumulative)
            order.avg_fill_price = average
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_ListedBroker([order])))

        qty, notional, _ = OrderRepository(conn).fetch_fill_totals(order_id=order_id)
        assert (qty, notional) == (Decimal("10"), Decimal("1050"))
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.avg_cost == 105.0

    def test_a_filled_reply_with_no_filled_size_stays_unreported(self, caplog) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        empty = _looked_up_order("42", status=OrderStatus.FILLED, filled_qty=0.0)

        with caplog.at_level(logging.WARNING, logger="trading.services.execution.open_order_reconciliation"):
            outcome = reconcile_open_orders(
                conn, account, broker_factory=Mock(return_value=_LookupBroker({"42": empty}))
            )

        assert outcome.unreported_broker_order_ids == ["42"]
        order = OrderRepository(conn).fetch_by_id(order_id=order_id)
        assert order is not None and order.status == "submitted"
        assert "reported filled with no filled size" in caplog.text

    def test_a_listed_fill_with_no_price_is_unreported_and_the_log_names_why(self, caplog) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)
        priceless = _looked_up_order("42", status=OrderStatus.PARTIALLY_FILLED, filled_qty=4.0)
        priceless.avg_fill_price = None

        with caplog.at_level(logging.WARNING, logger="trading.services.execution.open_order_reconciliation"):
            outcome = reconcile_open_orders(
                conn, account, broker_factory=Mock(return_value=_ListedBroker([priceless]))
            )

        assert outcome.unreported_broker_order_ids == ["42"]
        assert "no average price" in caplog.text

    def test_a_lower_cumulative_commission_never_posts_a_negative_commission(self) -> None:
        conn = _make_db()
        _insert_account_row(conn)
        _, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers_web", id=1)

        for status, cumulative, commission in (
            (OrderStatus.PARTIALLY_FILLED, 4.0, 1.0),
            (OrderStatus.FILLED, 10.0, 0.0),
        ):
            order = _looked_up_order("42", status=status, filled_qty=cumulative)
            order.commission = commission
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_ListedBroker([order])))

        assert OrderRepository(conn).fetch_fill_totals(order_id=order_id)[2] == Decimal("1")

    def test_a_socket_order_reported_before_its_executions_is_not_posted_twice(self) -> None:
        """A broker that reports executions keeps its own fills; no cumulative fill is invented."""
        conn = _make_db()
        _insert_account_row(conn)
        book_id, order_id = _open_clean_order(conn, broker_order_id="42")
        account = make_broker_account(broker_type="interactive_brokers", id=1)

        class _SocketBroker(_ListedBroker):
            reports_executions = True

        before_executions = _looked_up_order("42", status=OrderStatus.PARTIALLY_FILLED, filled_qty=5.0)
        with_executions = _looked_up_order("42", status=OrderStatus.PARTIALLY_FILLED, filled_qty=5.0)
        with_executions.fills = [
            OrderFill(filled_qty=5.0, fill_price=151.0, fill_time="2024-01-02T10:00:00Z", commission=0.0, exec_id="E1")
        ]
        for order in (before_executions, with_executions, with_executions):
            reconcile_open_orders(conn, account, broker_factory=Mock(return_value=_SocketBroker([order])))

        repo = OrderRepository(conn)
        assert repo.fetch_fill_exec_ids(order_id=order_id) == {"E1"}
        assert repo.fetch_fill_totals(order_id=order_id)[0] == Decimal("5")
        position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
        assert position is not None
        assert position.qty == 5.0
