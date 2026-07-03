from __future__ import annotations

from unittest.mock import Mock

import trading.services.sleeves.execution as sleeve_execution
from trading.repositories.sleeve_positions import SleevePositionRepository
from trading.repositories.sleeves import SleeveRepository
from trading.services.accounts import get_account
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


def _insert_sleeve(
    conn,
    *,
    account_id: int,
    name: str,
    status: str = "active",
    current_cash: float = 1_000.0,
) -> int:
    return insert_test_sleeve(
        conn,
        account_id=account_id,
        name=name,
        status=status,
        start_equity=current_cash,
        current_cash=current_cash,
        current_equity=current_cash,
    )


def test_generate_sleeve_trade_intents_uses_active_sleeves_and_assignments(conn, monkeypatch) -> None:
    account_name = "acct_sleeve_intents"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_assigned = _insert_sleeve(conn, account_id=account_id, name="assigned")
    sleeve_default = _insert_sleeve(conn, account_id=account_id, name="default")
    _insert_sleeve(conn, account_id=account_id, name="paused", status="paused")
    SleeveRepository(conn).insert_assignment(
        sleeve_id=sleeve_assigned,
        strategy_name="mean_reversion",
        param_set_id=None,
        effective_from="2026-05-03T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    account = get_account(conn, account_name)

    monkeypatch.setattr(
        sleeve_execution.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        sleeve_execution,
        "_prepare_trade_selection",
        Mock(return_value=("buy", "AAPL", 1, 101.0, None, None)),
    )

    intents = sleeve_execution.generate_sleeve_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=2,
        fee=0.0,
    )

    assert len(intents) == 2
    assert {intent.sleeve_id for intent in intents} == {sleeve_assigned, sleeve_default}
    strategies_by_sleeve = {intent.sleeve_id: intent.strategy_name for intent in intents}
    assert strategies_by_sleeve[sleeve_assigned] == "mean_reversion"
    assert strategies_by_sleeve[sleeve_default] == "Trend"


def test_prepare_trade_selection_delegates_to_auto_trading_execution(monkeypatch) -> None:
    recorder = Mock(return_value=("buy", "SPY", 1, 100.0, None, None))
    monkeypatch.setattr("trading.services.auto_trading.execution.prepare_trade_selection", recorder)

    result = sleeve_execution._prepare_trade_selection("account", "trend", feature_history_fn=None)

    assert result == ("buy", "SPY", 1, 100.0, None, None)
    recorder.assert_called_once_with("account", "trend", feature_history_fn=None)


def test_build_sleeve_state_skips_non_positive_positions(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_state")
    sleeve_id = _insert_sleeve(conn, account_id=account_id, name="stateful", current_cash=750.0)
    pos_repo = SleevePositionRepository(conn)
    pos_repo.upsert(
        sleeve_id=sleeve_id,
        symbol="AAPL",
        qty=2.0,
        avg_cost=100.0,
        market_value=210.0,
        unrealized_pnl=10.0,
        updated_at="2026-05-03T00:00:00Z",
    )
    pos_repo.upsert(
        sleeve_id=sleeve_id,
        symbol="MSFT",
        qty=0.0,
        avg_cost=200.0,
        market_value=0.0,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T00:00:00Z",
    )
    pos_repo.upsert(
        sleeve_id=sleeve_id,
        symbol="TSLA",
        qty=-1.0,
        avg_cost=300.0,
        market_value=-300.0,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T00:00:00Z",
    )

    state = sleeve_execution._build_sleeve_state(conn, sleeve_id=sleeve_id, current_cash=750.0)

    assert state.cash == 750.0
    assert state.positions == {"AAPL": 2.0}
    assert state.avg_cost == {"AAPL": 100.0}


def test_generate_sleeve_trade_intents_returns_empty_without_active_sleeves(conn) -> None:
    account_name = "acct_sleeve_none"
    account_id = insert_repository_account(conn, name=account_name)
    _insert_sleeve(conn, account_id=account_id, name="paused", status="paused")
    account = get_account(conn, account_name)

    intents = sleeve_execution.generate_sleeve_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )

    assert intents == []


def test_generate_sleeve_trade_intents_uses_default_universe_for_invalid_trade_universes(
    conn,
    monkeypatch,
) -> None:
    account_name = "acct_sleeve_invalid_universe"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = _insert_sleeve(conn, account_id=account_id, name="invalid-universe")
    SleeveRepository(conn).update_trade_universes(
        sleeve_id=sleeve_id,
        trade_universes='{"name": "not-a-list"}',
        updated_at="2026-05-03T00:00:00Z",
    )
    account = get_account(conn, account_name)
    captured_universes: list[list[str]] = []

    monkeypatch.setattr(
        sleeve_execution.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        sleeve_execution,
        "resolve_named_universes",
        lambda _names: (_ for _ in ()).throw(AssertionError("named universes should not be resolved")),
    )
    monkeypatch.setattr(
        sleeve_execution,
        "_prepare_trade_selection",
        lambda *_args, **_kwargs: captured_universes.append(list(_args[4])) or None,
    )

    intents = sleeve_execution.generate_sleeve_trade_intents(
        conn,
        account=account,
        universe=["SPY", "QQQ"],
        prices={"SPY": 500.0, "QQQ": 400.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )

    assert intents == []
    assert captured_universes == [["SPY", "QQQ"]]


def test_run_sleeve_mode_for_account_returns_generated_intent_count(conn, monkeypatch) -> None:
    account_name = "acct_sleeve_mode_count"
    account_id = insert_repository_account(conn, name=account_name)
    _insert_sleeve(conn, account_id=account_id, name="s1")
    _insert_sleeve(conn, account_id=account_id, name="s2")
    account = get_account(conn, account_name)

    monkeypatch.setattr(
        sleeve_execution.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        sleeve_execution,
        "_prepare_trade_selection",
        Mock(return_value=("buy", "MSFT", 1, 300.0, None, None)),
    )

    generated = sleeve_execution.run_sleeve_mode_for_account(
        conn,
        account=account,
        universe=["MSFT"],
        prices={"MSFT": 300.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
    )
    assert generated == 1
