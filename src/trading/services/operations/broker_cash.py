"""Totals the cash that books hold, per broker cash pool.

Accounts that reach one broker account share one real cash balance, so their books draw on it
together. This service only reads.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from decimal import Decimal

from trading.domain.broker_cash import broker_cash_pool
from trading.models import AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository


def account_cash_pool(account: AccountRecord) -> str | None:
    """The broker cash pool *account*'s books draw on, or None for an account whose broker keeps no cash."""
    return broker_cash_pool(account.broker_type, account.broker_host, account.broker_port)


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
