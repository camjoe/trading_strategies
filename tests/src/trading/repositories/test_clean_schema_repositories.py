"""Round-trip and invariant-guard tests for the P3 clean-schema repositories."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.init import ensure_db
from trading.repositories.feature_providers import FeatureProviderRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository, OrderUnitAccountMismatchError
from trading.repositories.positions import PositionRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.repositories.strategies import StrategyImmutableError, StrategyRepository
from trading.repositories.trading_units import TradingUnitRepository
from trading.repositories.unit_assignments import UnitAssignmentRepository
from trading.repositories.unit_settings import (
    UnitExecutionSettingsRepository,
    UnitOptionSettingsRepository,
    UnitRotationSettingsRepository,
)

NOW = "2026-07-03T12:00:00Z"


@pytest.fixture
def conn(tmp_path: Path):
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading.db"))
    connection = ensure_db()
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)


def _insert_account(conn, name: str = "acct_repo") -> int:
    cursor = conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at) VALUES (?, 'trend', 5000, ?)",
        (name, NOW),
    )
    return int(cursor.lastrowid)


def _insert_unit(conn, *, name: str = "default", is_default: int = 1) -> tuple[int, int]:
    account_id = _insert_account(conn, name=f"acct_{name}_{is_default}")
    unit_id = TradingUnitRepository(conn).insert(
        account_id=account_id,
        name=name,
        is_default=is_default,
        start_equity=5000.0,
        current_cash=5000.0,
        current_equity=5000.0,
        created_at=NOW,
        updated_at=NOW,
    )
    return account_id, unit_id


def _insert_strategy(conn, key: str = "trend_v1") -> int:
    return StrategyRepository(conn).insert(
        strategy_key=key,
        primitive="trend",
        params_json='{"fast_window": 10, "slow_window": 20}',
        style="trend",
        created_at=NOW,
        updated_at=NOW,
    )


def test_trading_unit_round_trip_and_default_lookup(conn) -> None:
    account_id, unit_id = _insert_unit(conn)

    repo = TradingUnitRepository(conn)
    unit = repo.fetch_by_id(unit_id=unit_id)
    assert unit is not None
    assert unit.account_id == account_id
    assert unit.is_default == 1

    default = repo.fetch_default_for_account(account_id=account_id)
    assert default is not None and default.id == unit_id

    repo.update_balances(unit_id=unit_id, current_cash=4200.0, current_equity=5100.0, updated_at=NOW)
    updated = repo.fetch_by_id(unit_id=unit_id)
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
        required_features=None,
        updated_at=NOW,
    )

    # Frozen rows are immutable (invariant 5) — tuning means a new row.
    repo.freeze(strategy_id=strategy_id, updated_at=NOW)
    with pytest.raises(StrategyImmutableError):
        repo.update_draft_knobs(
            strategy_id=strategy_id,
            primitive="trend",
            params_json='{"fast_window": 2}',
            required_features=None,
            updated_at=NOW,
        )

    repo.set_enabled(strategy_id=strategy_id, enabled=0, updated_at=NOW)
    assert repo.fetch_enabled() == []


def test_unit_assignment_rotation_keeps_single_open_row(conn) -> None:
    _, unit_id = _insert_unit(conn)
    first = _insert_strategy(conn, key="trend_v1")
    second = _insert_strategy(conn, key="meanrev_v1")
    repo = UnitAssignmentRepository(conn)

    repo.assign_strategy(unit_id=unit_id, strategy_id=first, effective_from=NOW, created_at=NOW, updated_at=NOW)
    repo.assign_strategy(
        unit_id=unit_id,
        strategy_id=second,
        effective_from="2026-07-04T12:00:00Z",
        created_at=NOW,
        updated_at=NOW,
    )

    open_assignment = repo.fetch_open(unit_id=unit_id)
    assert open_assignment is not None
    assert open_assignment.strategy_id == second
    history = repo.fetch_history(unit_id=unit_id)
    assert len(history) == 2
    assert history[0].effective_to == "2026-07-04T12:00:00Z"
    assert history[0].is_incumbent == 0


def test_unit_settings_upsert_and_fetch_round_trip(conn) -> None:
    _, unit_id = _insert_unit(conn)

    execution_repo = UnitExecutionSettingsRepository(conn)
    execution_repo.upsert(unit_id=unit_id, risk_policy="fixed_stop", stop_loss_pct=5.0, created_at=NOW, updated_at=NOW)
    execution_repo.upsert(
        unit_id=unit_id, risk_policy="stop_and_target", stop_loss_pct=4.0, created_at=NOW, updated_at=NOW
    )
    execution = execution_repo.fetch(unit_id=unit_id)
    assert execution is not None
    assert execution.risk_policy == "stop_and_target"
    assert execution.stop_loss_pct == pytest.approx(4.0)

    option_repo = UnitOptionSettingsRepository(conn)
    option_repo.upsert(unit_id=unit_id, option_type="call", option_min_dte=120, created_at=NOW, updated_at=NOW)
    option = option_repo.fetch(unit_id=unit_id)
    assert option is not None and option.option_type == "call"

    rotation_repo = UnitRotationSettingsRepository(conn)
    rotation_repo.upsert(unit_id=unit_id, rotation_enabled=1, rotation_mode="time", created_at=NOW, updated_at=NOW)
    rotation = rotation_repo.fetch(unit_id=unit_id)
    assert rotation is not None and rotation.rotation_enabled == 1

    # Missing row → None (callers fall back to code defaults per D4).
    _, other_unit = _insert_unit(conn, name="other")
    assert execution_repo.fetch(unit_id=other_unit) is None


def test_order_round_trip_and_unit_account_integrity_guard(conn) -> None:
    account_id, unit_id = _insert_unit(conn)
    other_account_id = _insert_account(conn, name="acct_other")
    repo = OrderRepository(conn)

    order_id = repo.insert(
        unit_id=unit_id,
        account_id=account_id,
        symbol="AAPL",
        side="buy",
        qty=2.0,
        requested_price=100.0,
        status="submitted",
        submitted_at=NOW,
        updated_at=NOW,
    )
    assert [order.id for order in repo.fetch_open_for_account(account_id=account_id)] == [order_id]

    repo.update_status(order_id=order_id, status="filled", filled_qty=2.0, avg_fill_price=100.5, updated_at=NOW)
    filled = repo.fetch_by_id(order_id=order_id)
    assert filled is not None
    assert filled.status == "filled"
    assert filled.avg_fill_price == pytest.approx(100.5)
    assert repo.fetch_open_for_account(account_id=account_id) == []

    # Invariant 4: the order's unit must belong to the order's account.
    with pytest.raises(OrderUnitAccountMismatchError):
        repo.insert(
            unit_id=unit_id,
            account_id=other_account_id,
            symbol="MSFT",
            side="buy",
            qty=1.0,
            status="submitted",
            submitted_at=NOW,
            updated_at=NOW,
        )


def test_position_and_ledger_round_trips(conn) -> None:
    account_id, unit_id = _insert_unit(conn)

    positions = PositionRepository(conn)
    positions.upsert(
        unit_id=unit_id,
        symbol="AAPL",
        qty=2.0,
        avg_cost=100.0,
        market_value=210.0,
        unrealized_pnl=10.0,
        updated_at=NOW,
    )
    positions.upsert(
        unit_id=unit_id, symbol="AAPL", qty=3.0, avg_cost=101.0, market_value=310.0, unrealized_pnl=7.0, updated_at=NOW
    )
    fetched = positions.fetch(unit_id=unit_id, symbol="AAPL")
    assert fetched is not None and fetched.qty == pytest.approx(3.0)
    assert len(positions.fetch_for_account(account_id=account_id)) == 1

    ledger = LedgerRepository(conn)
    ledger.insert(unit_id=unit_id, entry_type="deposit", amount=5000.0, entry_time=NOW, created_at=NOW)
    ledger.insert(
        unit_id=unit_id,
        entry_type="trade",
        amount=-303.0,
        reference_type="order",
        reference_id="7",
        entry_time=NOW,
        created_at=NOW,
    )
    entries = ledger.fetch_for_unit(unit_id=unit_id)
    assert [entry.entry_type for entry in entries] == ["deposit", "trade"]
    assert len(ledger.fetch_by_reference(reference_type="order", reference_id="7")) == 1

    with pytest.raises(sqlite3.IntegrityError):
        ledger.insert(unit_id=unit_id, entry_type="not_a_type", amount=1.0, entry_time=NOW, created_at=NOW)


def test_risk_and_feature_provider_round_trips(conn) -> None:
    account_id, unit_id = _insert_unit(conn)

    snapshots = RiskSnapshotRepository(conn)
    snapshots.insert(
        account_id=account_id,
        snapshot_time=NOW,
        gross_exposure=1.2,
        net_exposure=0.8,
        max_symbol_concentration_pct=25.0,
        max_sector_concentration_pct=40.0,
    )
    latest = snapshots.fetch_latest(account_id=account_id)
    assert latest is not None and latest.gross_exposure == pytest.approx(1.2)

    decisions = RiskDecisionRepository(conn)
    decisions.insert(
        account_id=account_id,
        unit_id=unit_id,
        decision_time=NOW,
        symbol="AAPL",
        side="buy",
        action="block",
        reason_code="stale_price_data",
        created_at=NOW,
    )
    recent = decisions.fetch_recent(account_id=account_id)
    assert len(recent) == 1
    assert recent[0].action == "block"

    providers = FeatureProviderRepository(conn)
    providers.upsert(provider_key="news", enabled=1, created_at=NOW, updated_at=NOW)
    providers.upsert(provider_key="news", enabled=0, created_at=NOW, updated_at=NOW)
    assert providers.fetch_enabled() == []
    fetched_provider = providers.fetch_by_key(provider_key="news")
    assert fetched_provider is not None and fetched_provider.enabled == 0
