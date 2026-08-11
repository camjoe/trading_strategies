"""Round-trip and invariant-guard tests for the clean-schema repositories."""

from __future__ import annotations

import sqlite3

import pytest

from common.time import utc_now_iso
from trading.models.books import RiskDecisionInsert, RiskSnapshotInsert
from trading.models.orders import OrderInsert
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.book_rotation_settings import BookRotationSettingsRepository
from trading.repositories.book_strategy_history import BookStrategyHistoryRepository
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import BookAccountMismatchError, OrderRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.repositories.strategies import StrategyImmutableError, StrategyRepository

NOW = "2026-07-03T12:00:00Z"


def _insert_account(conn, name: str = "acct_repo") -> int:
    cursor = conn.execute(
        "INSERT INTO accounts (name, initial_cash, created_at, updated_at) VALUES (?, 5000, ?, ?)",
        (name, NOW, NOW),
    )
    return int(cursor.lastrowid)


def _insert_book(conn, *, name: str = "default", is_default: int = 1) -> tuple[int, int]:
    account_id = _insert_account(conn, name=f"acct_{name}_{is_default}")
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name=name,
        is_default=is_default,
        start_equity=5000.0,
        current_cash=5000.0,
        current_equity=5000.0,
        created_at=NOW,
        updated_at=NOW,
    )
    return account_id, book_id


def _insert_strategy(conn, key: str = "trend_v1") -> int:
    return StrategyRepository(conn).insert(
        strategy_key=key,
        primitive="trend",
        params_json='{"fast_window": 10, "slow_window": 20}',
        created_at=NOW,
        updated_at=NOW,
    )


def test_book_round_trip_and_default_lookup(conn) -> None:
    account_id, book_id = _insert_book(conn)

    repo = BookRepository(conn)
    book = repo.fetch_by_id(book_id=book_id)
    assert book is not None
    assert book.account_id == account_id
    assert book.is_default == 1

    default = repo.fetch_default_for_account(account_id=account_id)
    assert default is not None and default.id == book_id

    repo.update_balances(book_id=book_id, current_cash=4200.0, current_equity=5100.0, updated_at=NOW)
    updated = repo.fetch_by_id(book_id=book_id)
    assert updated is not None
    assert updated.current_cash == pytest.approx(4200.0)
    assert updated.current_equity == pytest.approx(5100.0)


def test_strategy_round_trip_and_immutability_guard(conn) -> None:
    strategy_id = _insert_strategy(conn)
    repo = StrategyRepository(conn)

    fetched = repo.fetch_by_key(strategy_key="trend_v1")
    assert fetched is not None and fetched.id == strategy_id
    assert fetched.status == "draft"

    # Draft rows are editable.
    repo.update_draft_knobs(
        strategy_id=strategy_id,
        primitive="trend",
        params_json='{"fast_window": 5, "slow_window": 15}',
        updated_at=NOW,
    )

    # Frozen rows are immutable (invariant 5) — tuning means a new row.
    repo.freeze(strategy_id=strategy_id, updated_at=NOW)
    with pytest.raises(StrategyImmutableError):
        repo.update_draft_knobs(
            strategy_id=strategy_id,
            primitive="trend",
            params_json='{"fast_window": 2}',
            updated_at=NOW,
        )

    repo.set_enabled(strategy_id=strategy_id, enabled=0, updated_at=NOW)
    assert repo.fetch_enabled() == []


def test_immutability_guard_leaves_an_enclosing_unit_of_work_intact(conn) -> None:
    strategy_id = _insert_strategy(conn)
    repo = StrategyRepository(conn)
    repo.freeze(strategy_id=strategy_id, updated_at=NOW)

    # The guard rejects the edit but must not end the enclosing transaction: a
    # caller that handles it and carries on still gets the scope's other writes.
    with unit_of_work(conn):
        repo.set_enabled(strategy_id=strategy_id, enabled=0, updated_at=NOW)
        with pytest.raises(StrategyImmutableError):
            repo.update_draft_knobs(
                strategy_id=strategy_id,
                primitive="trend",
                params_json='{"fast_window": 2}',
                updated_at=NOW,
            )

    frozen = repo.fetch_by_id(strategy_id=strategy_id)
    assert frozen is not None and frozen.enabled == 0


def test_book_assignment_rotation_keeps_single_open_row(conn) -> None:
    _, book_id = _insert_book(conn)
    first = _insert_strategy(conn, key="trend_v1")
    second = _insert_strategy(conn, key="meanrev_v1")
    repo = BookStrategyHistoryRepository(conn)

    repo.assign_strategy(book_id=book_id, strategy_id=first, effective_from=NOW, created_at=NOW, updated_at=NOW)
    repo.assign_strategy(
        book_id=book_id,
        strategy_id=second,
        effective_from="2026-07-04T12:00:00Z",
        created_at=NOW,
        updated_at=NOW,
    )

    open_assignment = repo.fetch_open(book_id=book_id)
    assert open_assignment is not None
    assert open_assignment.strategy_id == second
    history = repo.fetch_history(book_id=book_id)
    assert len(history) == 2
    # The first assignment is now closed; the incumbent is the open row.
    assert history[0].effective_to == "2026-07-04T12:00:00Z"
    assert history[1].effective_to is None


def test_book_settings_upsert_and_fetch_round_trip(conn) -> None:
    _, book_id = _insert_book(conn)

    # Execution settings are book columns since revision 0004.
    book_repo = BookRepository(conn)
    book_repo.update(
        book_id=book_id,
        values={"risk_policy": "fixed_stop", "stop_loss_pct": 5.0},
        updated_at=utc_now_iso(),
    )
    book_repo.update(
        book_id=book_id,
        values={"risk_policy": "stop_and_target", "stop_loss_pct": 4.0},
        updated_at=utc_now_iso(),
    )
    execution = book_repo.fetch_by_id(book_id=book_id)
    assert execution is not None
    assert execution.risk_policy == "stop_and_target"
    assert execution.stop_loss_pct == pytest.approx(4.0)

    # Option settings are book columns since revision 0005.
    book_repo.update(
        book_id=book_id,
        values={"option_type": "call", "option_min_dte": 120},
        updated_at=utc_now_iso(),
    )
    option = book_repo.fetch_by_id(book_id=book_id)
    assert option is not None and option.option_type == "call"
    assert option.option_min_dte == 120

    rotation_repo = BookRotationSettingsRepository(conn)
    rotation_repo.upsert_rotation_scheduling(
        book_id=book_id, rotation_enabled=1, rotation_lookback_days=45, created_at=NOW, updated_at=NOW
    )
    rotation = rotation_repo.fetch(book_id=book_id)
    assert rotation is not None and rotation.rotation_enabled == 1
    assert rotation.rotation_lookback_days == 45

    # A fresh book carries the execution DDL defaults.
    _, other_book = _insert_book(conn, name="other")
    fresh = book_repo.fetch_by_id(book_id=other_book)
    assert fresh is not None
    assert fresh.risk_policy == "none"
    assert fresh.stop_loss_pct is None


def test_book_rotation_policy_upsert_preserves_scheduling_columns(conn) -> None:
    _, book_id = _insert_book(conn)
    rotation_repo = BookRotationSettingsRepository(conn)
    rotation_repo.upsert_rotation_scheduling(
        book_id=book_id, rotation_enabled=1, rotation_lookback_days=45, created_at=NOW, updated_at=NOW
    )

    rotation_repo.upsert_rotation_policy(
        book_id=book_id,
        min_trades_in_window=5,
        outperformance_threshold_bps=40.0,
        cooldown_days=10,
        risk_adjusted_return_weight=None,
        stability_weight=0.5,
        drawdown_penalty_weight=None,
        regime_fit_weight=None,
        created_at=NOW,
        updated_at=NOW,
    )

    saved = rotation_repo.fetch(book_id=book_id)
    assert saved is not None
    assert saved.rotation_enabled == 1
    assert saved.rotation_lookback_days == 45
    assert saved.min_trades_in_window == 5
    assert saved.outperformance_threshold_bps == pytest.approx(40.0)
    assert saved.cooldown_days == 10
    assert saved.stability_weight == pytest.approx(0.5)
    assert saved.risk_adjusted_return_weight is None


def test_book_rotation_scheduling_upsert_preserves_policy_columns(conn) -> None:
    _, book_id = _insert_book(conn)
    rotation_repo = BookRotationSettingsRepository(conn)
    rotation_repo.upsert_rotation_policy(
        book_id=book_id,
        min_trades_in_window=5,
        outperformance_threshold_bps=None,
        cooldown_days=10,
        risk_adjusted_return_weight=None,
        stability_weight=None,
        drawdown_penalty_weight=None,
        regime_fit_weight=None,
        created_at=NOW,
        updated_at=NOW,
    )

    rotation_repo.upsert_rotation_scheduling(
        book_id=book_id, rotation_enabled=1, rotation_lookback_days=45, created_at=NOW, updated_at=NOW
    )

    saved = rotation_repo.fetch(book_id=book_id)
    assert saved is not None
    assert saved.rotation_enabled == 1
    assert saved.rotation_lookback_days == 45
    assert saved.min_trades_in_window == 5
    assert saved.cooldown_days == 10


def test_order_round_trip_and_book_account_integrity_guard(conn) -> None:
    account_id, book_id = _insert_book(conn)
    other_account_id = _insert_account(conn, name="acct_other")
    repo = OrderRepository(conn)

    order_id = repo.insert(
        OrderInsert(
            book_id=book_id,
            account_id=account_id,
            symbol="AAPL",
            side="buy",
            qty=2.0,
            requested_price=100.0,
            status="submitted",
            submitted_at=NOW,
            updated_at=NOW,
        )
    )
    assert [order.id for order in repo.fetch_open_for_account(account_id=account_id)] == [order_id]

    repo.update_status(order_id=order_id, status="filled", filled_qty=2.0, avg_fill_price=100.5, updated_at=NOW)
    filled = repo.fetch_by_id(order_id=order_id)
    assert filled is not None
    assert filled.status == "filled"
    assert filled.avg_fill_price == pytest.approx(100.5)
    assert repo.fetch_open_for_account(account_id=account_id) == []

    # Invariant 4: the order's book must belong to the order's account.
    with pytest.raises(BookAccountMismatchError):
        repo.insert(
            OrderInsert(
                book_id=book_id,
                account_id=other_account_id,
                symbol="MSFT",
                side="buy",
                qty=1.0,
                status="submitted",
                submitted_at=NOW,
                updated_at=NOW,
            )
        )


def test_position_and_ledger_round_trips(conn) -> None:
    account_id, book_id = _insert_book(conn)

    positions = PositionRepository(conn)
    positions.upsert(
        book_id=book_id,
        symbol="AAPL",
        qty=2.0,
        avg_cost=100.0,
        market_value=210.0,
        unrealized_pnl=10.0,
        updated_at=NOW,
    )
    positions.upsert(
        book_id=book_id, symbol="AAPL", qty=3.0, avg_cost=101.0, market_value=310.0, unrealized_pnl=7.0, updated_at=NOW
    )
    fetched = positions.fetch(book_id=book_id, symbol="AAPL")
    assert fetched is not None and fetched.qty == pytest.approx(3.0)
    assert len(positions.fetch_for_account(account_id=account_id)) == 1

    ledger = LedgerRepository(conn)
    ledger.insert(book_id=book_id, entry_type="deposit", amount=5000.0, entry_time=NOW, created_at=NOW)
    ledger.insert(
        book_id=book_id,
        entry_type="trade",
        amount=-303.0,
        reference_type="order",
        reference_id="7",
        entry_time=NOW,
        created_at=NOW,
    )
    entries = ledger.fetch_for_book(book_id=book_id)
    assert [entry.entry_type for entry in entries] == ["deposit", "trade"]
    assert [(entry.reference_type, entry.reference_id) for entry in entries] == [(None, None), ("order", "7")]

    with pytest.raises(sqlite3.IntegrityError):
        ledger.insert(book_id=book_id, entry_type="not_a_type", amount=1.0, entry_time=NOW, created_at=NOW)


def test_risk_round_trips(conn) -> None:
    account_id, book_id = _insert_book(conn)

    snapshots = RiskSnapshotRepository(conn)
    snapshots.insert(
        RiskSnapshotInsert(
            account_id=account_id,
            snapshot_time=NOW,
            gross_exposure=1.2,
            net_exposure=0.8,
            max_symbol_concentration_pct=25.0,
            max_sector_concentration_pct=40.0,
        )
    )
    latest = snapshots.fetch_latest(account_id=account_id)
    assert latest is not None and latest.gross_exposure == pytest.approx(1.2)

    decisions = RiskDecisionRepository(conn)
    decisions.insert(
        RiskDecisionInsert(
            account_id=account_id,
            book_id=book_id,
            decision_time=NOW,
            symbol="AAPL",
            side="buy",
            action="block",
            reason_code="stale_price_data",
            created_at=NOW,
        )
    )
    recent = decisions.fetch_recent(account_id=account_id)
    assert len(recent) == 1
    assert recent[0].action == "block"


def test_submission_count_sees_orders_that_never_filled(conn) -> None:
    """Submitted orders count for pacing even when nothing fills."""
    account_id, book_id = _insert_book(conn, name="pacing")
    repo = OrderRepository(conn)
    for index in range(3):
        repo.insert(
            OrderInsert(
                book_id=book_id,
                account_id=account_id,
                symbol=f"SYM{index}",
                side="buy",
                qty=1.0,
                status="submitted",
                submitted_at="2026-01-15T10:00:30Z",
                updated_at="2026-01-15T10:00:30Z",
            )
        )

    window = {"start_iso": "2026-01-15T10:00:00Z", "end_iso": "2026-01-15T10:01:00Z"}
    assert repo.fetch_submission_count_between(**window) == 3
    assert repo.fetch_fill_count_between(**window) == 0
    assert repo.fetch_submission_count_between(start_iso="2026-01-15T11:00:00Z", end_iso="2026-01-15T11:01:00Z") == 0


def _submit_order(conn, *, account_id: int, book_id: int, symbol: str, status: str, submitted_at: str) -> int:
    return OrderRepository(conn).insert(
        OrderInsert(
            book_id=book_id,
            account_id=account_id,
            symbol=symbol,
            side="buy",
            qty=1.0,
            status=status,
            submitted_at=submitted_at,
            updated_at=submitted_at,
        )
    )


def test_status_filtered_fetches_include_partially_filled_orders(conn) -> None:
    """Both status filters span two statuses; a partial fill is real trading and a live order."""
    account_id, book_id = _insert_book(conn, name="partials")
    day = "2026-07-03"
    for symbol, status in (
        ("FILLED", "filled"),
        ("PARTIAL", "partially_filled"),
        ("SUBMITTED", "submitted"),
        ("CANCELLED", "cancelled"),
    ):
        _submit_order(
            conn, account_id=account_id, book_id=book_id, symbol=symbol, status=status, submitted_at=f"{day}T12:00:00Z"
        )

    repo = OrderRepository(conn)
    filled = repo.fetch_filled_for_book_on_date(book_id=book_id, date_str=day)
    assert sorted(order.symbol for order in filled) == ["FILLED", "PARTIAL"]

    still_open = repo.fetch_open_for_account(account_id=account_id)
    assert sorted(order.symbol for order in still_open) == ["PARTIAL", "SUBMITTED"]
