from unittest.mock import Mock

import pytest

from trading.domain.feature_provider import FeatureFetcherSet
from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import run_for_account
import trading.services.auto_trading.runtime as runtime_service
import trading.services.auto_trading.runtime_rotation as rotation_runtime_service
from tests.src.trading.services.auto_trading.factories import (
    RuntimeScenario,
    make_account_state,
    make_auto_trading_account,
)


def test_select_runtime_rotation_strategy_passes_runtime_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    account = make_auto_trading_account(id=12)
    calls: dict[str, object] = {}

    def _fake_select(conn, selected_account, as_of_iso):
        calls.update({"conn": conn, "account": selected_account, "as_of_iso": as_of_iso})
        return "mean_reversion"

    monkeypatch.setattr(rotation_runtime_service, "select_account_rotation_strategy_impl", _fake_select)

    selected = rotation_runtime_service.select_runtime_rotation_strategy(
        conn=object(),
        account=account,
        as_of_iso="2026-03-21T00:00:00Z",
    )

    assert selected == "mean_reversion"
    assert calls["account"] == account
    assert calls["as_of_iso"] == "2026-03-21T00:00:00Z"


def test_rotate_runtime_account_delegates_to_champion_challenger(monkeypatch: pytest.MonkeyPatch) -> None:
    account = make_auto_trading_account(id=14, strategy="trend")
    rotated_account = make_auto_trading_account(id=14, strategy="mean_reversion")
    update_rotation_state = Mock()
    get_account = Mock(return_value=rotated_account)
    is_rotation_due = Mock(return_value=True)
    observed: dict[str, object] = {}

    def _fake_select(conn, selected_account, as_of_iso):
        assert as_of_iso == "2026-03-23T00:00:00Z"
        return "mean_reversion"

    def _fake_rotate(conn, account_name, current_account, now_iso, deps):
        observed["conn"] = conn
        observed["due"] = deps.is_rotation_due_fn(current_account)
        observed["selected"] = deps.select_optimal_strategy_fn(conn, current_account, now_iso)
        observed["refetched"] = deps.get_account_fn(conn, account_name)
        observed["update_fn"] = deps.update_account_rotation_state_fn
        return rotated_account

    monkeypatch.setattr(rotation_runtime_service, "select_runtime_rotation_strategy", _fake_select)
    monkeypatch.setattr(rotation_runtime_service, "rotate_runtime_account_if_due_impl", _fake_rotate)

    # No episode sync any more: rotate_runtime_account only builds deps + delegates.
    rotated = rotation_runtime_service.rotate_runtime_account(
        conn=object(),
        account_name="acct_runtime",
        account=account,
        now_iso="2026-03-23T00:00:00Z",
        is_rotation_due_fn=is_rotation_due,
        update_account_rotation_state_fn=update_rotation_state,
        get_account_fn=get_account,
    )

    assert rotated == rotated_account
    assert observed["due"] is True
    assert observed["selected"] == "mean_reversion"
    assert observed["refetched"] == rotated_account
    assert observed["update_fn"] is update_rotation_state


def test_run_for_account_uses_rotated_active_strategy(monkeypatch) -> None:
    initial_account = make_auto_trading_account(
        id=11,
        strategy="trend",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=0,
        rotation_last_at="2026-03-01T00:00:00Z",
        rotation_active_strategy="trend",
    )
    rotated_account = make_auto_trading_account(
        id=11,
        strategy="mean_reversion",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=1,
        rotation_last_at="2026-03-17T00:00:00Z",
        rotation_active_strategy="mean_reversion",
    )
    scenario = RuntimeScenario(
        account=initial_account,
        rotated_account=rotated_account,
        state=make_account_state(),
        prepared_selection=("buy", "AAPL", 1, 100.0, None, None),
        now_values=["2026-03-17T00:00:00Z"] * 3,
    )
    scenario.install(monkeypatch, runtime_service)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=Mock(return_value=scenario.broker),
        feature_fetchers=FeatureFetcherSet(fetch_policy=Mock()),
    )

    assert executed == 1
    args, _kwargs = scenario.trade_recorder.call_args
    assert args[6] == "mean_reversion"
