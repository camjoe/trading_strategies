from __future__ import annotations

import json
from unittest.mock import Mock

import pandas as pd

import trading.services.execution.selection.book_intents as book_intents
from tests.support.backtesting import bar_frame
from tests.support.books import assign_test_book_strategy, insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.strategies import StrategyRepository
from trading.services.accounts import get_account


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
        book_intents.auto_trader_policy,
        "order_risk_breaches",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        book_intents,
        "prepare_book_trades",
        Mock(return_value=[("buy", "AAPL", 1, 101.0, None, None)]),
    )

    intents = book_intents.generate_book_trade_intents(
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
    _assign(conn, book_id=book_id, strategy_name="trend")

    rising = bar_frame(pd.Series([float(i) for i in range(1, 41)]))
    flat = bar_frame(pd.Series([100.0] * 40))

    buy_intents = book_intents.generate_book_trade_intents(
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
    hold_intents = book_intents.generate_book_trade_intents(
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
        created_at="2026-07-12T00:00:00Z",
        updated_at="2026-07-12T00:00:00Z",
    )
    account_name = "acct_variant_signal"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = _insert_book(conn, account_id=account_id, name="variant")
    account = get_account(conn, account_name)
    _assign(conn, book_id=book_id, strategy_name="trend_fast")

    rising = bar_frame(pd.Series([float(i) for i in range(1, 41)]))
    intents = book_intents.generate_book_trade_intents(
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

    state = book_intents._build_book_state(conn, book_id=book_id)

    assert state.cash == 750.0
    assert state.positions == {"AAPL": 2.0}
    assert state.avg_cost == {"AAPL": 100.0}


def test_generate_book_trade_intents_returns_empty_without_active_books(conn) -> None:
    account_name = "acct_book_none"
    account_id = insert_repository_account(conn, name=account_name)
    _insert_book(conn, account_id=account_id, name="paused", status="paused")
    account = get_account(conn, account_name)

    intents = book_intents.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
    )

    assert intents == []


def _captured_book_universe(conn, monkeypatch, *, account_name: str, stored_symbols: str) -> list[list[str]]:
    """Run intent generation for a book holding *stored_symbols*, capturing what it selected over."""
    account_id = insert_repository_account(conn, name=account_name)
    book_id = _insert_book(conn, account_id=account_id, name=account_name)
    BookRepository(conn).update_trade_symbols(
        book_id=book_id,
        trade_symbols=stored_symbols,
        updated_at="2026-05-03T00:00:00Z",
    )
    _assign(conn, book_id=book_id, strategy_name="trend")
    captured: list[list[str]] = []

    monkeypatch.setattr(
        book_intents.auto_trader_policy,
        "order_risk_breaches",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        book_intents,
        "prepare_book_trades",
        # positional args: (account, strategy_name, params, state, forced_sell, universe, ...)
        lambda *_args, **_kwargs: captured.append(list(_args[5])) or [],
    )

    intents = book_intents.generate_book_trade_intents(
        conn,
        account=get_account(conn, account_name),
        universe=["SPY", "QQQ"],
        prices={"SPY": 500.0, "QQQ": 400.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
    )
    assert intents == []
    return captured


def test_generate_book_trade_intents_selects_over_the_books_stored_symbols(conn, monkeypatch) -> None:
    captured = _captured_book_universe(
        conn,
        monkeypatch,
        account_name="acct_book_symbols",
        stored_symbols='["NVDA","AMD"]',
    )

    assert captured == [["NVDA", "AMD"]]


def test_generate_book_trade_intents_falls_back_to_the_run_universe_for_unusable_symbols(
    conn,
    monkeypatch,
) -> None:
    """A malformed or empty column must not silently narrow the book to nothing."""
    assert _captured_book_universe(
        conn,
        monkeypatch,
        account_name="acct_book_bad_symbols",
        stored_symbols='{"name": "not-a-list"}',
    ) == [["SPY", "QQQ"]]
    assert _captured_book_universe(
        conn,
        monkeypatch,
        account_name="acct_book_empty_symbols",
        stored_symbols="[]",
    ) == [["SPY", "QQQ"]]


def _multi_signal_book(conn, *, account_name: str, cash: float = 100_000.0) -> tuple[int, object]:
    account_id = insert_repository_account(conn, name=account_name)
    book_id = _insert_book(conn, account_id=account_id, name=account_name, current_cash=cash)
    BookRepository(conn).update_trade_symbols(
        book_id=book_id,
        trade_symbols=json.dumps(["AAPL", "MSFT", "NVDA"]),
        updated_at="2026-05-03T00:00:00Z",
    )
    _assign(conn, book_id=book_id, strategy_name="trend")
    return book_id, get_account(conn, account_name)


def _rising_histories() -> dict[str, pd.DataFrame]:
    rising = bar_frame(pd.Series([float(i) for i in range(1, 41)]))
    return {"AAPL": rising, "MSFT": rising, "NVDA": rising}


def test_generate_book_trade_intents_emits_more_than_one_trade_per_book(conn) -> None:
    """The account cap counts trades, not books."""
    _, account = _multi_signal_book(conn, account_name="acct_budget_multi")

    intents = book_intents.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL", "MSFT", "NVDA"],
        prices={"AAPL": 10.0, "MSFT": 10.0, "NVDA": 10.0},
        iv_rank_proxy={},
        max_trades=3,
        fee=0.0,
        histories=_rising_histories(),
    )

    assert len(intents) == 3
    assert {intent.symbol for intent in intents} == {"AAPL", "MSFT", "NVDA"}


def test_generate_book_trade_intents_respects_the_account_cap(conn) -> None:
    _, account = _multi_signal_book(conn, account_name="acct_budget_account_cap")

    intents = book_intents.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL", "MSFT", "NVDA"],
        prices={"AAPL": 10.0, "MSFT": 10.0, "NVDA": 10.0},
        iv_rank_proxy={},
        max_trades=2,
        fee=0.0,
        histories=_rising_histories(),
    )

    assert len(intents) == 2


def _two_contending_books(conn, *, account_name: str) -> tuple[int, int, object]:
    """Two identically-configured books competing for one trade's worth of budget."""
    account_id = insert_repository_account(conn, name=account_name)
    book_ids = []
    for name in ("first", "second"):
        book_id = _insert_book(conn, account_id=account_id, name=name, current_cash=100_000.0)
        BookRepository(conn).update_trade_symbols(
            book_id=book_id,
            trade_symbols=json.dumps(["AAPL"]),
            updated_at="2026-05-03T00:00:00Z",
        )
        _assign(conn, book_id=book_id, strategy_name="trend")
        book_ids.append(book_id)
    return book_ids[0], book_ids[1], get_account(conn, account_name)


def _budget_winner(conn, account, *, seed: str) -> int:
    intents = book_intents.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL"],
        prices={"AAPL": 10.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        histories=_rising_histories(),
        selection_seed=seed,
    )
    assert len(intents) == 1
    return intents[0].book_id


def test_account_trade_budget_is_not_always_taken_by_the_lowest_book_id(conn) -> None:
    """Books are enumerated by id; that must not decide who gets account capacity."""
    first, second, account = _two_contending_books(conn, account_name="acct_book_claim_order")

    winners = {_budget_winner(conn, account, seed=f"2026-07-{day:02d}") for day in range(1, 29)}

    assert winners == {first, second}


def test_account_trade_budget_claim_is_reproducible_from_the_seed(conn) -> None:
    """Varied across runs, but a given run's outcome must reproduce from the audit trail."""
    _, _, account = _two_contending_books(conn, account_name="acct_book_claim_seeded")

    assert _budget_winner(conn, account, seed="2026-07-30") == _budget_winner(conn, account, seed="2026-07-30")


def test_generate_book_trade_intents_respects_max_trades_per_run(conn) -> None:
    """A book's own limit narrows the account cap."""
    book_id, account = _multi_signal_book(conn, account_name="acct_budget_book_cap")
    BookRepository(conn).update_settings_columns(
        book_id=book_id,
        updates=["max_trades_per_run = ?"],
        params=[1],
    )

    intents = book_intents.generate_book_trade_intents(
        conn,
        account=account,
        universe=["AAPL", "MSFT", "NVDA"],
        prices={"AAPL": 10.0, "MSFT": 10.0, "NVDA": 10.0},
        iv_rank_proxy={},
        max_trades=3,
        fee=0.0,
        histories=_rising_histories(),
    )

    assert len(intents) == 1
