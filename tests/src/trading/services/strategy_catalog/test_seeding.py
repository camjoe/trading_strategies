from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.init import ensure_db
from trading.domain.strategy_signals import PRIMITIVE_CATALOG
from trading.repositories.strategies import StrategyRepository
from trading.repositories.trading_units import TradingUnitRepository
from trading.repositories.unit_assignments import UnitAssignmentRepository
from trading.repositories.unit_settings import (
    UnitExecutionSettingsRepository,
    UnitRotationSettingsRepository,
)
from trading.services.strategy_catalog import ensure_default_units, seed_strategy_catalog

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


def test_seed_strategy_catalog_creates_all_primitives_idempotently(conn) -> None:
    inserted = seed_strategy_catalog(conn, now_iso=NOW)
    assert inserted == len(PRIMITIVE_CATALOG)

    # Idempotent: nothing added on re-run.
    assert seed_strategy_catalog(conn, now_iso=NOW) == 0

    repo = StrategyRepository(conn)
    trend = repo.fetch_by_key(strategy_key="trend")
    assert trend is not None
    assert trend.primitive == "trend"
    assert trend.status == "draft"
    assert json.loads(trend.params_json) == dict(PRIMITIVE_CATALOG["trend"].knob_schema)
    assert trend.style == PRIMITIVE_CATALOG["trend"].style

    news = repo.fetch_by_key(strategy_key="news_sentiment")
    assert news is not None
    assert news.style == "alternative"
    assert news.required_features is not None
    assert json.loads(news.required_features) == list(PRIMITIVE_CATALOG["news_sentiment"].required_features)


def test_ensure_default_units_bootstraps_unit_settings_and_assignment(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)
    conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at) VALUES ('acct_seed', 'trend', 5000, ?)",
        (NOW,),
    )
    conn.execute(
        """
        UPDATE accounts
        SET risk_policy = 'stop_and_target', stop_loss_pct = 4.0, learning_enabled = 1,
            rotation_enabled = 1, rotation_regime_strategy_risk_on = 'trend',
            goal_min_return_pct = 2.0, trade_universes = '["core"]'
        WHERE name = 'acct_seed'
        """
    )
    conn.commit()
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'acct_seed'").fetchone()[0])

    created = ensure_default_units(conn, now_iso=NOW)
    assert created == 1
    assert ensure_default_units(conn, now_iso=NOW) == 0  # idempotent

    unit = TradingUnitRepository(conn).fetch_default_for_account(account_id=account_id)
    assert unit is not None
    assert unit.is_default == 1
    assert unit.start_equity == pytest.approx(5000.0)
    assert unit.goal_min_return_pct == pytest.approx(2.0)
    assert unit.trade_universes == '["core"]'

    execution = UnitExecutionSettingsRepository(conn).fetch(unit_id=unit.id)
    assert execution is not None
    assert execution.risk_policy == "stop_and_target"
    assert execution.stop_loss_pct == pytest.approx(4.0)
    assert execution.learning_enabled == 1

    rotation = UnitRotationSettingsRepository(conn).fetch(unit_id=unit.id)
    assert rotation is not None
    assert rotation.rotation_enabled == 1
    trend_id = StrategyRepository(conn).fetch_by_key(strategy_key="trend")
    assert trend_id is not None
    assert rotation.regime_strategy_risk_on_id == trend_id.id

    assignment = UnitAssignmentRepository(conn).fetch_open(unit_id=unit.id)
    assert assignment is not None
    assert assignment.strategy_id == trend_id.id


def test_ensure_default_units_skips_unknown_legacy_strategy_label(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)
    conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at) VALUES ('acct_odd', 'Momentum Growth X', 1000, ?)",
        (NOW,),
    )
    conn.commit()
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'acct_odd'").fetchone()[0])

    assert ensure_default_units(conn, now_iso=NOW) == 1
    unit = TradingUnitRepository(conn).fetch_default_for_account(account_id=account_id)
    assert unit is not None
    # Unknown label → no assignment opened; unit still bootstrapped.
    assert UnitAssignmentRepository(conn).fetch_open(unit_id=unit.id) is None
