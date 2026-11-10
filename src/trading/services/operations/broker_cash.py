"""Totals the cash that books hold, per broker cash pool.

Accounts that reach one broker account share one real cash balance, so their books draw on it
together. This service only reads.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from trading.domain.broker_cash import broker_cash_pool
from trading.models import AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository


def account_cash_pool(account: AccountRecord) -> str | None:
    """The broker cash pool *account*'s books draw on, or None for an account whose broker keeps no cash."""
    return broker_cash_pool(account.broker_type, account.broker_host, account.broker_port)


def fetch_pool_mates_outside_run(conn: sqlite3.Connection, run_account_names: Sequence[str]) -> list[str]:
    """Names of the accounts that share a broker cash pool with a run account but are not in the run."""
    accounts = AccountRepository(conn).fetch_all()
    run = set(run_account_names)
    pools = {account_cash_pool(account) for account in accounts if account.name in run} - {None}
    return [account.name for account in accounts if account.name not in run and account_cash_pool(account) in pools]


def fetch_book_cash_by_pool(conn: sqlite3.Connection) -> dict[str, Decimal]:
    """Sum the cash of every book, whatever its status, of every account in each broker cash pool.

    A paused book still holds real cash, so it counts. Accounts with no pool are left out.
    """
    books = BookRepository(conn)
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for account in AccountRepository(conn).fetch_all():
        pool = account_cash_pool(account)
        if pool is None:
            continue
        totals[pool] += sum(
            (book.current_cash for book in books.fetch_for_account(account_id=account.id)),
            Decimal(0),
        )
    return dict(totals)
