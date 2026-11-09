from __future__ import annotations

import sqlite3
from decimal import Decimal

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.services.operations.broker_cash import fetch_book_cash_by_broker_type


def _set_broker_type(conn: sqlite3.Connection, account_id: int, broker_type: str) -> None:
    conn.execute("UPDATE accounts SET broker_type = ? WHERE id = ?", (broker_type, account_id))
    conn.commit()


def test_cash_is_summed_across_every_book_of_every_account_of_a_broker_type(conn: sqlite3.Connection) -> None:
    first = insert_repository_account(conn, name="ibkr_a", initial_cash=5000.0)
    second = insert_repository_account(conn, name="ibkr_b", initial_cash=2000.0)
    simulator = insert_repository_account(conn, name="sim", initial_cash=700.0)
    _set_broker_type(conn, first, "interactive_brokers_web_paper")
    _set_broker_type(conn, second, "interactive_brokers_web_paper")
    _set_broker_type(conn, simulator, "paper")
    insert_test_book(conn, account_id=first, name="core", current_cash=5000.0)
    insert_test_book(conn, account_id=first, name="second_book", current_cash=1234.5)
    insert_test_book(conn, account_id=second, name="core", current_cash=2000.0)
    insert_test_book(conn, account_id=simulator, name="core", current_cash=700.0)

    totals = fetch_book_cash_by_broker_type(conn)

    assert totals["interactive_brokers_web_paper"] == Decimal("5000") + Decimal("1234.5") + Decimal("2000")
    assert totals["paper"] == Decimal("700")


def test_no_accounts_means_no_totals(conn: sqlite3.Connection) -> None:
    assert fetch_book_cash_by_broker_type(conn) == {}
