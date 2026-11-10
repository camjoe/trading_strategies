from __future__ import annotations

import sqlite3
from decimal import Decimal

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.services.operations.broker_cash import fetch_book_cash_by_pool, fetch_pool_mates_outside_run

WEB = "interactive_brokers_web_paper"
SOCKET = "interactive_brokers_socket_paper"


def _account(
    conn: sqlite3.Connection,
    name: str,
    broker_type: str,
    *,
    port: int | None = None,
    books: tuple[tuple[str, float, str], ...] = (),
) -> int:
    account_id = insert_repository_account(conn, name=name)
    conn.execute("UPDATE accounts SET broker_type = ?, broker_port = ? WHERE id = ?", (broker_type, port, account_id))
    conn.commit()
    for book_name, cash, status in books:
        insert_test_book(conn, account_id=account_id, name=book_name, current_cash=cash, status=status)
    return account_id


def test_cash_is_summed_across_every_book_of_every_account_in_a_pool(conn: sqlite3.Connection) -> None:
    _account(conn, "web_a", WEB, books=(("core", 5000.0, "active"), ("second", 1234.5, "active")))
    _account(conn, "web_b", "interactive_brokers_web", books=(("core", 2000.0, "active"),))
    _account(conn, "sim", "paper", books=(("core", 700.0, "active"),))

    assert fetch_book_cash_by_pool(conn) == {"ibkr_web": Decimal("8234.5")}


def test_a_paused_book_still_counts(conn: sqlite3.Connection) -> None:
    _account(conn, "web_a", WEB, books=(("core", 100.0, "active"), ("idle", 40.0, "paused")))

    assert fetch_book_cash_by_pool(conn) == {"ibkr_web": Decimal("140")}


def test_socket_accounts_on_different_ports_are_separate_pools(conn: sqlite3.Connection) -> None:
    _account(conn, "sock_a", SOCKET, port=4002, books=(("core", 10.0, "active"),))
    _account(conn, "sock_b", SOCKET, port=4003, books=(("core", 20.0, "active"),))
    _account(conn, "sock_c", SOCKET, port=4002, books=(("core", 5.0, "active"),))

    totals = fetch_book_cash_by_pool(conn)

    assert sorted(totals.values()) == [Decimal("15"), Decimal("20")]


def test_no_accounts_means_no_totals(conn: sqlite3.Connection) -> None:
    assert fetch_book_cash_by_pool(conn) == {}


def test_pool_mates_are_the_accounts_sharing_a_pool_with_the_run_but_not_in_it(conn: sqlite3.Connection) -> None:
    _account(conn, "web_a", WEB)
    _account(conn, "web_b", "interactive_brokers_web")
    _account(conn, "sim", "paper")
    _account(conn, "sock_a", SOCKET, port=4002)
    _account(conn, "sock_b", SOCKET, port=4003)

    assert fetch_pool_mates_outside_run(conn, ["web_a"]) == ["web_b"]
    assert fetch_pool_mates_outside_run(conn, ["web_a", "web_b"]) == []
    assert fetch_pool_mates_outside_run(conn, ["sim"]) == []
    assert fetch_pool_mates_outside_run(conn, ["sock_a", "sim"]) == []
