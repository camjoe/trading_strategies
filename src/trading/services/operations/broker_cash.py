"""Totals the cash that books hold, per broker type.

Every account of one broker type trades through one broker account, so their books draw on one
real cash balance. This service only reads.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from decimal import Decimal

from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository


def fetch_book_cash_by_broker_type(conn: sqlite3.Connection) -> dict[str, Decimal]:
    """Sum every book's cash across all accounts, keyed by the account's broker type.

    Accounts with no broker type are keyed ``""``.
    """
    books = BookRepository(conn)
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for account in AccountRepository(conn).fetch_all():
        totals[account.broker_type or ""] += sum(
            (book.current_cash for book in books.fetch_for_account(account_id=account.id)),
            Decimal(0),
        )
    return dict(totals)
