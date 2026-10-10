"""Fractional-share fills and cash events keep the exact cash invariant.

Regression guard for the money-representation review finding: the ledger's
gross-trade and fee entries and ``books.current_cash`` were truncated on separate
grids, so ``current_cash - start_equity`` drifted from ``SUM(ledger.amount)`` by a
minor unit per fractional fill. ``apply_book_fill`` and the manual cash-event path
now snap both sides to one grid, so ``check_cash_invariant`` reports no divergence.

The prices and quantities here are chosen so the gross value has more than six
decimal places — the case whole-share fixtures never reach.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.data_ops.check_cash_invariant import invariant_payload
from tests.support.repositories import insert_repository_account
from trading.repositories.books import BookRepository
from trading.services.execution.ledger.mutations import record_trade
from trading.services.execution.submission import apply_book_fill


@pytest.fixture
def book_env(conn: sqlite3.Connection) -> tuple[str, int, int]:
    account_name = "frac_acct"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name="default",
        is_default=1,
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-07-21T00:00:00Z",
        updated_at="2026-07-21T00:00:00Z",
    )
    return account_name, account_id, book_id


def _assert_reconciles(conn: sqlite3.Connection) -> None:
    payload = invariant_payload(conn)
    assert payload["divergent"] == []


def test_fractional_buy_reconciles_exactly(conn: sqlite3.Connection, book_env) -> None:
    _account_name, _account_id, book_id = book_env
    apply_book_fill(
        conn,
        book_id=book_id,
        order_id=1,
        side="buy",
        symbol="AAPL",
        fill_qty=0.333333,
        fill_price=100.55,
        transaction_cost=1.0035,
        fill_time="2026-07-21T10:00:00Z",
    )
    _assert_reconciles(conn)


def test_many_fractional_fills_do_not_accumulate_drift(conn: sqlite3.Connection, book_env) -> None:
    _account_name, _account_id, book_id = book_env
    for index in range(10):
        apply_book_fill(
            conn,
            book_id=book_id,
            order_id=index + 1,
            side="buy",
            symbol="AAPL",
            fill_qty=0.111111,
            fill_price=137.77 + index,
            transaction_cost=1.0035,
            fill_time=f"2026-07-21T10:{index:02d}:00Z",
        )
    # A per-fill divergence of one minor unit would sum to ten across the ledger;
    # the grid snap keeps every fill exact, so the total is still zero.
    _assert_reconciles(conn)


def test_fractional_sell_reconciles_exactly(conn: sqlite3.Connection, book_env) -> None:
    _account_name, _account_id, book_id = book_env
    apply_book_fill(
        conn,
        book_id=book_id,
        order_id=1,
        side="buy",
        symbol="AAPL",
        fill_qty=2.5,
        fill_price=88.88,
        transaction_cost=1.0,
        fill_time="2026-07-21T10:00:00Z",
    )
    apply_book_fill(
        conn,
        book_id=book_id,
        order_id=2,
        side="sell",
        symbol="AAPL",
        fill_qty=1.333333,
        fill_price=91.17,
        transaction_cost=0.9999,
        fill_time="2026-07-21T11:00:00Z",
    )
    _assert_reconciles(conn)


def test_fractional_cash_events_reconcile_exactly(conn: sqlite3.Connection, book_env) -> None:
    account_name, _account_id, book_id = book_env
    # Deposit and withdrawal amounts with a sub-cent tail exercise the settlement
    # path's grid snap (a withdrawal was the divergent direction).
    record_trade(conn, account_name, "buy", "CASH", 1.0, 250.3333335, 0.0, "2026-07-21T09:00:00Z", None)
    record_trade(conn, account_name, "sell", "CASH", 1.0, 50.7777775, 0.0, "2026-07-21T09:30:00Z", None)
    _assert_reconciles(conn)
