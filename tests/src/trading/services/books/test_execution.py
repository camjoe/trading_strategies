from __future__ import annotations

import json
from unittest.mock import Mock

import pandas as pd

import trading.services.books.execution as book_execution
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.strategies import StrategyRepository
from trading.services.accounts import get_account
from tests.support.repositories import insert_repository_account
from tests.support.books import assign_test_book_strategy, insert_test_book


def _insert_book(
    conn,
    *,
    account_id: int,
    name: str,
    status: str = "active",
    current_cash: float = 1_000.0,
) -> int:
    return insert_test_book(
        conn,
        account_id=account_id,
        name=name,
        status=status,
        start_equity=current_cash,
        current_cash=current_cash,
        current_equity=current_cash,
    )


def _assign(conn, *, book_id: int, strategy_name: str) -> None:
    assign_test_book_strategy(conn, book_id=book_id, strategy_name=strategy_name)


def test_generate_book_trade_intents_uses_active_books_and_assignments(conn, monkeypatch) -> None:
    account_name = "acct_book_intents"
    account_id = insert_repository_account(conn, name=account_name)
    book_mr = _insert_book(conn, account_id=account_id, name="mean-rev")
    book_trend = _insert_book(conn, account_id=account_id, name="trend")
    _insert_book(conn, account_id=account_id, name="unassigned")
    _insert_book(conn, account_id=account_id, name="paused", status="paused")
    _assign(conn, book_id=book_mr, strategy_name="mean_reversion")
    _assign(conn, book_id=book_trend, strategy_name="trend")
    account = get_account(conn, account_name)

    monkeypatch.setattr(
        book_execution.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        book_execution,
        "_prepare_trade_selection",
        Mock(return_value=("buy", "AAPL", 1, 101.0, None, None)),
    )

    intents = book_execution.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        max_trades=4,
        fee=0.0,
    )

    # Only the two assigned books trade; the unassigned and paused books are skipped.
    assert {intent.book_id for intent in intents} == {book_mr, book_trend}
    strategies_by_book = {intent.book_id: intent.strategy_name for intent in intents}
    assert strategies_by_book[book_mr] == "mean_reversion"
    assert strategies_by_book[book_trend] == "trend"


def test_generate_book_trade_intents_are_signal_driven(conn) -> None:
    account_name = "acct_book_signal"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = _insert_book(conn, account_id=account_id, name="signal")
    account = get_account(conn, account_name)
    _assign(conn, book_id=book_id, strategy_name=str(account.strategy))

    rising = pd.Series([float(i) for i in range(1, 41)])
    flat = pd.Series([100.0] * 40)

    buy_intents = book_execution.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 10.0},
        iv_rank_proxy={},
        max_trades=2,
        fee=0.0,
        histories={"AAPL": rising},
    )
    assert [(intent.side, intent.symbol) for intent in buy_intents] == [("buy", "AAPL")]

    # No forced minimum: a flat (hold) history yields zero intents.
    hold_intents = book_execution.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 10.0},
        iv_rank_proxy={},
        max_trades=2,
        fee=0.0,
        histories={"AAPL": flat},
    )
    assert hold_intents == []


def test_generate_book_trade_intents_runs_variant_under_its_primitive(conn) -> None:
    # A data variant: a distinct catalog key bound to the trend primitive. It
    # should trade on the trend signal while the intent keeps the variant label.
    StrategyRepository(conn).insert(
        strategy_key="trend_fast",
        primitive="trend",
        params_json=json.dumps({"fast_window": 5, "slow_window": 10}),
        style="trend",
        created_at="2026-07-12T00:00:00Z",
        updated_at="2026-07-12T00:00:00Z",
    )
    account_name = "acct_variant_signal"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = _insert_book(conn, account_id=account_id, name="variant")
    account = get_account(conn, account_name)
    _assign(conn, book_id=book_id, strategy_name="trend_fast")

    rising = pd.Series([float(i) for i in range(1, 41)])
    intents = book_execution.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 10.0},
        iv_rank_proxy={},
        max_trades=2,
        fee=0.0,
        histories={"AAPL": rising},
    )

    assert [(intent.side, intent.symbol) for intent in intents] == [("buy", "AAPL")]
    # Display/bookkeeping keeps the assigned variant key, not the primitive.
    assert intents[0].strategy_name == "trend_fast"


def test_prepare_trade_selection_delegates_to_auto_trading_execution(monkeypatch) -> None:
    recorder = Mock(return_value=("buy", "SPY", 1, 100.0, None, None))
    monkeypatch.setattr("trading.services.auto_trading.execution.prepare_trade_selection", recorder)

    result = book_execution._prepare_trade_selection("account", "trend", feature_history_fn=None)

    assert result == ("buy", "SPY", 1, 100.0, None, None)
    recorder.assert_called_once_with("account", "trend", feature_history_fn=None)


def test_build_book_state_reads_book_and_skips_non_positive_positions(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_book_state")
    # A book's state comes from the book itself (cash + positions).
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name="stateful",
        is_default=0,
        start_equity=750.0,
        current_cash=750.0,
        current_equity=750.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    pos_repo = PositionRepository(conn)
    pos_repo.upsert(
        book_id=book_id,
        symbol="AAPL",
        qty=2.0,
        avg_cost=100.0,
        market_value=210.0,
        unrealized_pnl=10.0,
        updated_at="2026-05-03T00:00:00Z",
    )
    pos_repo.upsert(
        book_id=book_id,
        symbol="MSFT",
        qty=0.0,
        avg_cost=200.0,
        market_value=0.0,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T00:00:00Z",
    )

    state = book_execution._build_book_state(conn, book_id=book_id)

    assert state.cash == 750.0
    assert state.positions == {"AAPL": 2.0}
    assert state.avg_cost == {"AAPL": 100.0}


def test_generate_book_trade_intents_returns_empty_without_active_books(conn) -> None:
    account_name = "acct_book_none"
    account_id = insert_repository_account(conn, name=account_name)
    _insert_book(conn, account_id=account_id, name="paused", status="paused")
    account = get_account(conn, account_name)

    intents = book_execution.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
    )

    assert intents == []


def test_generate_book_trade_intents_uses_default_universe_for_invalid_trade_universes(
    conn,
    monkeypatch,
) -> None:
    account_name = "acct_book_invalid_universe"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = _insert_book(conn, account_id=account_id, name="invalid-universe")
    BookRepository(conn).update_trade_universes(
        book_id=book_id,
        trade_universes='{"name": "not-a-list"}',
        updated_at="2026-05-03T00:00:00Z",
    )
    _assign(conn, book_id=book_id, strategy_name="trend")
    account = get_account(conn, account_name)
    captured_universes: list[list[str]] = []

    monkeypatch.setattr(
        book_execution.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        book_execution,
        "resolve_named_universes",
        lambda _names: (_ for _ in ()).throw(AssertionError("named universes should not be resolved")),
    )
    monkeypatch.setattr(
        book_execution,
        "_prepare_trade_selection",
        # positional args: (account, strategy_name, params, state, forced_sell, universe, ...)
        lambda *_args, **_kwargs: captured_universes.append(list(_args[5])) or None,
    )

    intents = book_execution.generate_book_trade_intents(
        conn,
        account=account,
        universe=["SPY", "QQQ"],
        prices={"SPY": 500.0, "QQQ": 400.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
    )

    assert intents == []
    assert captured_universes == [["SPY", "QQQ"]]


def test_run_multi_book_mode_for_account_returns_generated_intent_count(conn, monkeypatch) -> None:
    account_name = "acct_book_mode_count"
    account_id = insert_repository_account(conn, name=account_name)
    _assign(conn, book_id=_insert_book(conn, account_id=account_id, name="s1"), strategy_name="trend")
    _assign(conn, book_id=_insert_book(conn, account_id=account_id, name="s2"), strategy_name="trend")
    account = get_account(conn, account_name)

    monkeypatch.setattr(
        book_execution.auto_trader_policy,
        "choose_sell_ticker_by_risk",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        book_execution,
        "_prepare_trade_selection",
        Mock(return_value=("buy", "MSFT", 1, 300.0, None, None)),
    )

    generated = book_execution.run_multi_book_mode_for_account(
        conn,
        account=account,
        universe=["MSFT"],
        prices={"MSFT": 300.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
    )
    assert generated == 1
