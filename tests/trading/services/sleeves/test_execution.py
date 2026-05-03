from __future__ import annotations

from unittest.mock import Mock

import trading.services.sleeves.execution as sleeve_execution
from trading.repositories.sleeves import (
    insert_sleeve_strategy_assignment,
    insert_strategy_sleeve,
)
from trading.services.accounts import get_account
from tests.support.repositories import insert_repository_account


def _insert_sleeve(
    conn,
    *,
    account_id: int,
    name: str,
    status: str = "active",
    current_cash: float = 1_000.0,
) -> int:
    return insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name=name,
        status=status,
        base_ccy="USD",
        start_equity=current_cash,
        current_cash=current_cash,
        current_equity=current_cash,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )


def test_generate_sleeve_trade_intents_uses_active_sleeves_and_assignments(conn, monkeypatch) -> None:
    account_name = "acct_sleeve_intents"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_assigned = _insert_sleeve(conn, account_id=account_id, name="assigned")
    sleeve_default = _insert_sleeve(conn, account_id=account_id, name="default")
    _insert_sleeve(conn, account_id=account_id, name="paused", status="paused")
    insert_sleeve_strategy_assignment(
        conn,
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

    monkeypatch.setattr(sleeve_execution.random, "randint", lambda _a, _b: 2)
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


def test_run_sleeve_mode_for_account_returns_generated_intent_count(conn, monkeypatch) -> None:
    account_name = "acct_sleeve_mode_count"
    account_id = insert_repository_account(conn, name=account_name)
    _insert_sleeve(conn, account_id=account_id, name="s1")
    _insert_sleeve(conn, account_id=account_id, name="s2")
    account = get_account(conn, account_name)

    monkeypatch.setattr(sleeve_execution.random, "randint", lambda _a, _b: 1)
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
