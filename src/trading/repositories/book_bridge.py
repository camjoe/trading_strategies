"""Idempotent bridging resolution into the book-keyed tables.

Resolves an account to its default book, creating it bare if it is missing:
execution/option settings are DDL defaults on the books columns, and the
rotation settings row is intentionally absent — a missing row means code
defaults.

`create_account` now creates the book itself, so the bootstrap branch fires
only for accounts that predate that change; `ensure_default_books` is the
repair path for them. Once those are repaired this is a pure lookup, which
`BookRepository.fetch_default_for_account` already provides.
"""

from __future__ import annotations

import sqlite3


def default_book_id(conn: sqlite3.Connection, account_id: int) -> int:
    """Resolve (bootstrapping if needed) the account's default book id."""
    row = conn.execute(
        "SELECT id FROM books WHERE account_id = ? AND is_default = 1",
        (account_id,),
    ).fetchone()
    if row is not None:
        return int(row[0])
    # Goals/symbols are book-owned (revision 0008) — the account carries nothing
    # to copy. Symbols start empty because resolving a universe name is service
    # work (revision 0029); create_account applies the real set right after.
    # Every symbol set/change records history.
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash,
            current_equity, trade_symbols, created_at, updated_at
        )
        SELECT id, 'default', 'active', 1, initial_cash, initial_cash, initial_cash,
               '[]', created_at, created_at
        FROM accounts WHERE id = ?
        """,
        (account_id,),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"Account {account_id} does not exist; cannot resolve its default book.")
    book_id = int(cursor.lastrowid or 0)
    conn.execute(
        """
        INSERT INTO book_universe_history (book_id, trade_symbols, effective_from, effective_to)
        SELECT ?, '[]', created_at, NULL FROM accounts WHERE id = ?
        """,
        (book_id, account_id),
    )
    return book_id
