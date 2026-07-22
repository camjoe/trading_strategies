from __future__ import annotations

import pytest

from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.nav import mark_account_to_market, mark_book_to_market
from tests.support.repositories import insert_repository_account

AS_OF = "2026-07-05T12:00:00Z"


def _book(conn, *, account_id: int, name: str, is_default: int, cash: float) -> int:
    return BookRepository(conn).insert(
        account_id=account_id,
        name=name,
        is_default=is_default,
        start_equity=cash,
        current_cash=cash,
        current_equity=cash,
        created_at="2026-07-05T00:00:00Z",
        updated_at="2026-07-05T00:00:00Z",
    )


def _position(conn, *, book_id: int, symbol: str, qty: float, avg_cost: float) -> None:
    # Seed a position marked at cost (as a fresh fill would leave it).
    PositionRepository(conn).upsert(
        book_id=book_id,
        symbol=symbol,
        qty=qty,
        avg_cost=avg_cost,
        market_value=qty * avg_cost,
        unrealized_pnl=0.0,
        updated_at="2026-07-05T09:00:00Z",
    )


def test_mark_reflects_current_prices(conn):
    account_id = insert_repository_account(conn, name="nav_acct")
    book_id = _book(conn, account_id=account_id, name="default", is_default=1, cash=1_000.0)
    _position(conn, book_id=book_id, symbol="AAPL", qty=10.0, avg_cost=100.0)

    result = mark_book_to_market(conn, book_id=book_id, prices={"AAPL": 120.0}, as_of=AS_OF)

    # Equity = 1000 cash + 10 * 120 = 2200; unrealized = (120-100)*10 = 200.
    assert result.current_cash == pytest.approx(1_000.0)
    assert result.current_equity == pytest.approx(2_200.0)
    assert result.unpriced_symbols == []
    position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
    assert position is not None
    assert position.market_value == pytest.approx(1_200.0)
    assert position.unrealized_pnl == pytest.approx(200.0)
    book = BookRepository(conn).fetch_by_id(book_id=book_id)
    assert book is not None
    assert book.current_equity == pytest.approx(2_200.0)
    # Cash is never moved by marking.
    assert book.current_cash == pytest.approx(1_000.0)


def test_unpriced_symbol_falls_back_to_cost_basis(conn):
    account_id = insert_repository_account(conn, name="nav_unpriced")
    book_id = _book(conn, account_id=account_id, name="default", is_default=1, cash=500.0)
    _position(conn, book_id=book_id, symbol="MSFT", qty=4.0, avg_cost=50.0)

    # No mark for MSFT (missing / non-positive both fall back).
    result = mark_book_to_market(conn, book_id=book_id, prices={"MSFT": 0.0}, as_of=AS_OF)

    # Held at cost: 4 * 50 = 200 → equity 700, zero unrealized.
    assert result.unpriced_symbols == ["MSFT"]
    assert result.current_equity == pytest.approx(700.0)
    position = PositionRepository(conn).fetch(book_id=book_id, symbol="MSFT")
    assert position is not None
    assert position.unrealized_pnl == pytest.approx(0.0)


def test_empty_book_equity_equals_cash(conn):
    account_id = insert_repository_account(conn, name="nav_empty")
    book_id = _book(conn, account_id=account_id, name="default", is_default=1, cash=2_500.0)

    result = mark_book_to_market(conn, book_id=book_id, prices={}, as_of=AS_OF)

    assert result.current_equity == pytest.approx(2_500.0)
    assert result.unpriced_symbols == []


def test_mark_account_marks_every_book(conn):
    account_id = insert_repository_account(conn, name="nav_multi")
    default_book = _book(conn, account_id=account_id, name="default", is_default=1, cash=1_000.0)
    book_book = _book(conn, account_id=account_id, name="book_a", is_default=0, cash=500.0)
    _position(conn, book_id=default_book, symbol="AAPL", qty=10.0, avg_cost=100.0)
    _position(conn, book_id=book_book, symbol="AAPL", qty=5.0, avg_cost=100.0)

    results = mark_account_to_market(conn, account_id=account_id, prices={"AAPL": 110.0}, as_of=AS_OF)

    equity_by_book = {r.book_id: r.current_equity for r in results}
    assert equity_by_book[default_book] == pytest.approx(1_000.0 + 10 * 110.0)
    assert equity_by_book[book_book] == pytest.approx(500.0 + 5 * 110.0)


def test_missing_book_raises(conn):
    with pytest.raises(LookupError):
        mark_book_to_market(conn, book_id=999, prices={}, as_of=AS_OF)


def test_mark_rolls_back_position_when_balance_update_fails(conn, monkeypatch):
    account_id = insert_repository_account(conn, name="nav_rollback")
    book_id = _book(conn, account_id=account_id, name="default", is_default=1, cash=1_000.0)
    _position(conn, book_id=book_id, symbol="AAPL", qty=10.0, avg_cost=100.0)

    def fail_balance_update(*args, **kwargs) -> None:
        raise RuntimeError("balance update failed")

    monkeypatch.setattr(BookRepository, "update_balances", fail_balance_update)

    with pytest.raises(RuntimeError, match="balance update failed"):
        mark_book_to_market(conn, book_id=book_id, prices={"AAPL": 120.0}, as_of=AS_OF)

    position = PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL")
    assert position is not None
    assert position.market_value == pytest.approx(1_000.0)
    assert position.unrealized_pnl == pytest.approx(0.0)
