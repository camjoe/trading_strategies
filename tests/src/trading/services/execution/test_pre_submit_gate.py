from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from types import SimpleNamespace

from tests.src.trading.services.execution.helpers import insert_book_equity_snapshot
from tests.support.repositories import insert_repository_account
from trading.models.execution import BookTradeIntent, RiskGateDecision
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_RECONCILIATION_MISMATCH,
    KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING,
    KILL_SWITCH_REASON_STALE_PRICE_DATA,
)
from trading.services.execution.pre_submit_gate import BookPreSubmitGate

RUN_TIME = "2026-07-05T12:00:00Z"


class RecordingSink:
    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []

    def record(
        self,
        conn: sqlite3.Connection,
        *,
        account_id: int,
        snapshot_time: str,
        decisions: Sequence[RiskGateDecision],
        kill_switch_reasons: Sequence[str],
        kill_switch_triggered: bool,
    ) -> None:
        self.calls.append(
            SimpleNamespace(
                account_id=account_id,
                snapshot_time=snapshot_time,
                decisions=list(decisions),
                kill_switch_reasons=list(kill_switch_reasons),
                kill_switch_triggered=kill_switch_triggered,
            )
        )


def _book_env(conn, *, equity: float = 100_000.0) -> tuple[int, int]:
    account_id = insert_repository_account(conn, name="gate_acct")
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name="default",
        is_default=1,
        start_equity=equity,
        current_cash=equity,
        current_equity=equity,
        created_at="2026-07-05T00:00:00Z",
        updated_at="2026-07-05T00:00:00Z",
    )
    return account_id, book_id


def _snapshot(conn, book_id: int, *, equity: float, snapshot_time: str = RUN_TIME) -> None:
    insert_book_equity_snapshot(conn, book_id, equity=equity, snapshot_time=snapshot_time)


def _intent(
    book_id: int,
    account_id: int,
    *,
    side: str = "buy",
    symbol: str = "AAPL",
    qty: float = 10.0,
    price: float = 100.0,
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


def _gate(prices: dict[str, float], **kwargs) -> BookPreSubmitGate:
    return BookPreSubmitGate(prices=prices, snapshot_time=RUN_TIME, **kwargs)


# --- allow / rescale / block (notional gate honored) ------------------------


def test_allow_within_limits_passes_intent_through(conn):
    account_id, book_id = _book_env(conn, equity=100_000.0)
    _snapshot(conn, book_id, equity=100_000.0)

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, qty=10.0, price=100.0)]
    )

    assert result.kill_switch_reasons == []
    assert [i.qty for i in result.approved_intents] == [10.0]
    assert result.blocked_intents == []
    assert result.rescaled_intents == []


def test_rescale_trims_qty_to_cap(conn):
    # Book equity 1000 → per-book symbol cap = 1000 * 0.25 = 250 notional → max 2 @ 100.
    account_id, book_id = _book_env(conn, equity=1_000.0)
    _snapshot(conn, book_id, equity=1_000.0)

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, qty=10.0, price=100.0)]
    )

    assert result.kill_switch_reasons == []
    assert [i.qty for i in result.approved_intents] == [2.0]
    assert [i.qty for i in result.rescaled_intents] == [2.0]
    assert result.blocked_intents == []


def test_block_when_no_notional_headroom(conn):
    # Equity 50 → every cap under one share's notional → blocked.
    account_id, book_id = _book_env(conn, equity=50.0)
    _snapshot(conn, book_id, equity=50.0)

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, qty=1.0, price=100.0)]
    )

    assert result.kill_switch_reasons == []
    assert result.approved_intents == []
    assert len(result.blocked_intents) == 1


# --- kill switches ----------------------------------------------------------


def test_stale_price_kill_switch_holds_the_book(conn):
    account_id, book_id = _book_env(conn, equity=100_000.0)
    _snapshot(conn, book_id, equity=100_000.0)

    # No live mark for AAPL → stale-price fires even though the notional gate allowed it.
    result = _gate({}).evaluate(conn, account_id=account_id, intents=[_intent(book_id, account_id)])

    assert result.kill_switch_reasons == [KILL_SWITCH_REASON_STALE_PRICE_DATA]
    assert result.approved_intents == []


def test_reconciliation_snapshot_missing_kill_switch(conn):
    account_id, book_id = _book_env(conn, equity=100_000.0)
    # No snapshot inserted.

    result = _gate({"AAPL": 100.0}).evaluate(conn, account_id=account_id, intents=[_intent(book_id, account_id)])

    assert result.kill_switch_reasons == [KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING]
    assert result.approved_intents == []


def test_reconciliation_mismatch_kill_switch(conn):
    account_id, book_id = _book_env(conn, equity=100_000.0)
    # Fresh snapshot, but equity disagrees with the book roll-up beyond tolerance.
    _snapshot(conn, book_id, equity=90_000.0)

    result = _gate({"AAPL": 100.0}).evaluate(conn, account_id=account_id, intents=[_intent(book_id, account_id)])

    assert result.kill_switch_reasons == [KILL_SWITCH_REASON_RECONCILIATION_MISMATCH]
    assert result.approved_intents == []


# --- audit sink -------------------------------------------------------------


def test_audit_sink_receives_decisions_and_reasons(conn):
    account_id, book_id = _book_env(conn, equity=100_000.0)
    _snapshot(conn, book_id, equity=100_000.0)
    sink = RecordingSink()

    _gate({}, audit_sink=sink).evaluate(conn, account_id=account_id, intents=[_intent(book_id, account_id)])

    assert len(sink.calls) == 1
    call = sink.calls[0]
    assert call.account_id == account_id
    assert call.snapshot_time == RUN_TIME
    assert call.kill_switch_triggered is True
    assert KILL_SWITCH_REASON_STALE_PRICE_DATA in call.kill_switch_reasons
    # The notional-gate decision is captured for the audit trail (book_id in the bucket slot).
    assert len(call.decisions) == 1
    assert call.decisions[0].book_id == book_id


def test_sell_position_reduction_is_allowed(conn):
    account_id, book_id = _book_env(conn, equity=1_000.0)
    _snapshot(conn, book_id, equity=1_000.0)
    PositionRepository(conn).upsert(
        book_id=book_id,
        symbol="AAPL",
        qty=10.0,
        avg_cost=100.0,
        market_value=1000.0,
        unrealized_pnl=0.0,
        updated_at="2026-07-05T09:00:00Z",
    )

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, side="sell", qty=5.0, price=100.0)]
    )

    # Risk-reducing sells are always allowed regardless of caps.
    assert result.kill_switch_reasons == []
    assert [i.qty for i in result.approved_intents] == [5.0]


# --- drawdown breaker -------------------------------------------------------


def _drawn_down_book(conn) -> tuple[int, int]:
    """A book down 30% from a peak recorded earlier in its snapshot series.

    The latest snapshot has to match current book equity or reconciliation trips
    first and the breaker never gets a say.
    """
    account_id, book_id = _book_env(conn, equity=70_000.0)
    _snapshot(conn, book_id, equity=100_000.0, snapshot_time="2026-07-01T12:00:00Z")
    _snapshot(conn, book_id, equity=70_000.0)
    return account_id, book_id


def test_drawdown_breaker_blocks_buys_past_the_limit(conn):
    account_id, book_id = _drawn_down_book(conn)

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, qty=1.0, price=100.0)]
    )

    # Not a kill switch: the account keeps running, it just stops adding risk.
    assert result.kill_switch_reasons == []
    assert result.approved_intents == []
    assert [d.reason_code for d in result.decisions] == ["drawdown_breaker"]


def test_drawdown_breaker_leaves_the_exit_open(conn):
    account_id, book_id = _drawn_down_book(conn)
    PositionRepository(conn).upsert(
        book_id=book_id,
        symbol="AAPL",
        qty=10.0,
        avg_cost=100.0,
        market_value=1_000.0,
        unrealized_pnl=0.0,
        updated_at="2026-07-05T09:00:00Z",
    )

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, side="sell", qty=10.0, price=100.0)]
    )

    assert result.kill_switch_reasons == []
    assert [i.qty for i in result.approved_intents] == [10.0]


def test_shallow_drawdown_does_not_block_buys(conn):
    account_id, book_id = _book_env(conn, equity=95_000.0)
    _snapshot(conn, book_id, equity=100_000.0, snapshot_time="2026-07-01T12:00:00Z")
    _snapshot(conn, book_id, equity=95_000.0)

    result = _gate({"AAPL": 100.0}).evaluate(
        conn, account_id=account_id, intents=[_intent(book_id, account_id, qty=1.0, price=100.0)]
    )

    assert [i.qty for i in result.approved_intents] == [1.0]
