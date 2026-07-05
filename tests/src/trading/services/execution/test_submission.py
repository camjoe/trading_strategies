from __future__ import annotations

import sqlite3
from collections.abc import Sequence

import pytest

from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.execution.gate_result import GateResult
from trading.models.orders.broker_order import BrokerOrder, OrderFill, OrderStatus
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.gate import AllowAllGate
from trading.services.execution.submission import (
    KILL_SWITCH_REASON_BROKER_API_ANOMALY,
    LEDGER_ENTRY_TYPE_TRADE,
    LEDGER_REFERENCE_TYPE_ORDER,
    submit_book_intents,
)
from tests.support.repositories import insert_repository_account

# --- test doubles -----------------------------------------------------------


class FakeBroker:
    """Minimal BrokerConnection stand-in — only place_order is exercised."""

    def __init__(
        self,
        *,
        status: OrderStatus = OrderStatus.FILLED,
        broker_order_id: str | None = "B1",
        filled_qty: float | None = None,
        avg_fill_price: float | None = None,
        commission: float = 0.0,
        fills: list[OrderFill] | None = None,
        raises: bool = False,
    ) -> None:
        self._status = status
        self._broker_order_id = broker_order_id
        self._filled_qty = filled_qty
        self._avg_fill_price = avg_fill_price
        self._commission = commission
        self._fills = fills or []
        self._raises = raises
        self.calls: list[BrokerOrder] = []

    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        self.calls.append(order)
        if self._raises:
            raise RuntimeError("broker unavailable")
        order.broker_order_id = self._broker_order_id
        order.status = self._status
        if self._filled_qty is not None:
            order.filled_qty = self._filled_qty
        elif self._status == OrderStatus.FILLED:
            order.filled_qty = order.qty
        if self._avg_fill_price is not None:
            order.avg_fill_price = self._avg_fill_price
        elif self._status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
            order.avg_fill_price = order.price
        order.commission = self._commission
        order.submitted_at = "2026-07-05T10:00:00Z"
        order.updated_at = "2026-07-05T10:00:01Z"
        order.fills = list(self._fills)
        return order


class BlockingGate:
    """Gate that rejects every intent (no kill switch)."""

    def evaluate(
        self, conn: sqlite3.Connection, *, account_id: int, intents: Sequence[BookTradeIntent]
    ) -> GateResult:
        return GateResult(blocked_intents=list(intents))


class KillSwitchGate:
    """Gate that trips a kill switch, holding the whole book."""

    def __init__(self, reason: str = "stale_price_data") -> None:
        self._reason = reason

    def evaluate(
        self, conn: sqlite3.Connection, *, account_id: int, intents: Sequence[BookTradeIntent]
    ) -> GateResult:
        return GateResult(kill_switch_reasons=[self._reason])


# --- fixtures / helpers -----------------------------------------------------


@pytest.fixture
def book_env(conn):
    account_id = insert_repository_account(conn, name="exec_acct")
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name="default",
        is_default=1,
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-07-05T00:00:00Z",
        updated_at="2026-07-05T00:00:00Z",
    )
    return account_id, book_id


def _intent(
    book_id: int,
    account_id: int,
    *,
    side: str = "buy",
    symbol: str = "AAPL",
    qty: float = 10.0,
    price: float | None = 100.0,
) -> BookTradeIntent:
    return BookTradeIntent(
        book_id=book_id,
        account_id=account_id,
        strategy_id=None,
        symbol=symbol,
        side=side,
        qty=qty,
        requested_price=price,
    )


def _fills_for_book(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT f.* FROM order_fills f
        JOIN orders o ON o.id = f.order_id
        WHERE o.book_id = ?
        ORDER BY f.id
        """,
        (book_id,),
    ).fetchall()


# --- tests ------------------------------------------------------------------


def test_happy_fill_persists_order_fill_position_and_ledger(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(
        status=OrderStatus.FILLED,
        avg_fill_price=101.0,
        fills=[OrderFill(filled_qty=10.0, fill_price=101.0, fill_time="2026-07-05T10:00:01Z", commission=0.0, exec_id="E1")],
    )

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id, price=100.0)],
        broker=broker,
        gate=AllowAllGate(),
        fee=0.0,
    )

    assert result.submitted_count == 1
    assert result.filled_count == 1
    assert result.kill_switch_reasons == []
    assert len(result.order_ids) == 1

    order = OrderRepository(conn).fetch_by_id(order_id=result.order_ids[0])
    assert order is not None
    assert order.book_id == book_id
    assert order.account_id == account_id
    assert order.status == "filled"
    assert order.avg_fill_price == 101.0

    fills = _fills_for_book(conn, book_id)
    assert len(fills) == 1
    assert fills[0]["exec_id"] == "E1"

    position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
    assert position is not None
    assert position.qty == 10.0
    assert position.avg_cost == pytest.approx(101.0)

    ledger = LedgerRepository(conn).fetch_for_book(book_id=book_id)
    assert len(ledger) == 1
    assert ledger[0].entry_type == LEDGER_ENTRY_TYPE_TRADE
    assert ledger[0].reference_type == LEDGER_REFERENCE_TYPE_ORDER
    assert ledger[0].reference_id == str(result.order_ids[0])
    # Buy of 10 @ 101 with no fee/commission → cash out 1010.
    assert ledger[0].amount == pytest.approx(-1010.0)


def test_fee_folds_into_cost_basis_and_ledger(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(status=OrderStatus.FILLED, avg_fill_price=100.0)

    submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id, qty=10.0, price=100.0)],
        broker=broker,
        gate=AllowAllGate(),
        fee=5.0,
    )

    position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
    assert position is not None
    # (10*100 + 5 fee) / 10 shares = 100.5 avg cost.
    assert position.avg_cost == pytest.approx(100.5)
    ledger = LedgerRepository(conn).fetch_for_book(book_id=book_id)
    assert ledger[0].amount == pytest.approx(-1005.0)


def test_hold_persists_submitted_order_without_position_or_ledger(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(status=OrderStatus.SUBMITTED)

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id)],
        broker=broker,
        gate=AllowAllGate(),
        fee=0.0,
    )

    assert result.submitted_count == 1
    assert result.filled_count == 0
    order = OrderRepository(conn).fetch_by_id(order_id=result.order_ids[0])
    assert order is not None
    assert order.status == "submitted"
    assert PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL") is None
    assert LedgerRepository(conn).fetch_for_book(book_id=book_id) == []


def test_partial_fill_records_fills_but_defers_position_and_ledger(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(
        status=OrderStatus.PARTIALLY_FILLED,
        filled_qty=4.0,
        avg_fill_price=100.0,
        fills=[OrderFill(filled_qty=4.0, fill_price=100.0, fill_time="2026-07-05T10:00:01Z", commission=0.0, exec_id="P1")],
    )

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id, qty=10.0)],
        broker=broker,
        gate=AllowAllGate(),
        fee=0.0,
    )

    assert result.filled_count == 0
    order = OrderRepository(conn).fetch_by_id(order_id=result.order_ids[0])
    assert order is not None
    assert order.status == "partially_filled"
    assert order.filled_qty == 4.0
    assert len(_fills_for_book(conn, book_id)) == 1
    # Position + ledger only move on a completed fill (reconciliation completes partials).
    assert PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL") is None
    assert LedgerRepository(conn).fetch_for_book(book_id=book_id) == []


def test_broker_exception_appends_anomaly_and_stops(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(raises=True)

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id, symbol="AAPL"), _intent(book_id, account_id, symbol="MSFT")],
        broker=broker,
        gate=AllowAllGate(),
        fee=0.0,
    )

    assert KILL_SWITCH_REASON_BROKER_API_ANOMALY in result.kill_switch_reasons
    assert result.submitted_count == 0
    # Stopped on the first anomaly — the second intent is never attempted.
    assert len(broker.calls) == 1
    assert OrderRepository(conn).fetch_open_for_account(account_id=account_id) == []


def test_gate_kill_switch_submits_nothing(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(status=OrderStatus.FILLED)

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id)],
        broker=broker,
        gate=KillSwitchGate("stale_price_data"),
        fee=0.0,
    )

    assert result.kill_switch_reasons == ["stale_price_data"]
    assert result.submitted_count == 0
    assert broker.calls == []
    assert OrderRepository(conn).fetch_for_book(book_id=book_id) == []


def test_gate_block_skips_blocked_intents(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(status=OrderStatus.FILLED)

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id)],
        broker=broker,
        gate=BlockingGate(),
        fee=0.0,
    )

    assert result.submitted_count == 0
    assert result.blocked_count == 1
    assert broker.calls == []
    assert OrderRepository(conn).fetch_for_book(book_id=book_id) == []


def test_on_fill_callback_invoked_with_intent_and_order_id(conn, book_env):
    account_id, book_id = book_env
    broker = FakeBroker(status=OrderStatus.FILLED, avg_fill_price=100.0)
    seen: list[tuple[str, int]] = []

    submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id, symbol="AAPL")],
        broker=broker,
        gate=AllowAllGate(),
        fee=0.0,
        on_fill=lambda intent, order_id, placed: seen.append((intent.symbol, order_id)),
    )

    assert len(seen) == 1
    assert seen[0][0] == "AAPL"


def test_sell_reduces_position_and_credits_ledger(conn, book_env):
    account_id, book_id = book_env
    # Seed an existing long position to sell against.
    PositionRepository(conn).upsert(
        book_id=book_id,
        symbol="AAPL",
        qty=10.0,
        avg_cost=100.0,
        market_value=1000.0,
        unrealized_pnl=0.0,
        updated_at="2026-07-05T09:00:00Z",
    )
    broker = FakeBroker(status=OrderStatus.FILLED, avg_fill_price=110.0)

    result = submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[_intent(book_id, account_id, side="sell", qty=4.0, price=110.0)],
        broker=broker,
        gate=AllowAllGate(),
        fee=0.0,
    )

    position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
    assert position is not None
    assert position.qty == pytest.approx(6.0)
    ledger = LedgerRepository(conn).fetch_for_book(book_id=book_id)
    # Sell 4 @ 110 → cash in 440.
    assert ledger[0].amount == pytest.approx(440.0)
    assert result.filled_count == 1
