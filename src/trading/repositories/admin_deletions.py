"""Row-count queries supporting admin account deletion.

Deletion itself is a single ``DELETE FROM accounts`` statement
(``AccountRepository.delete_by_ids``); ``ON DELETE CASCADE`` removes every
account-owned row. These helpers exist so ``delete_accounts()`` can report what
a deletion removed (or, for dry runs, would remove).
"""

from __future__ import annotations

import sqlite3

from infrastructure.database.sql_helpers import in_placeholders

# Child tables reachable only through an owning parent keyed to accounts.
_CHILD_COUNT_PREDICATES = {
    "order_fills": "order_id IN (SELECT id FROM orders WHERE account_id IN ({placeholders}))",
    "equity_snapshots": "book_id IN (SELECT id FROM books WHERE account_id IN ({placeholders}))",
    "backtest_trades": "run_id IN (SELECT id FROM backtest_runs WHERE account_id IN ({placeholders}))",
    "backtest_equity_snapshots": "run_id IN (SELECT id FROM backtest_runs WHERE account_id IN ({placeholders}))",
    "walk_forward_group_runs": "group_id IN (SELECT id FROM walk_forward_groups WHERE account_id IN ({placeholders}))",
    "promotion_review_events": "review_id IN (SELECT id FROM promotion_reviews WHERE account_id IN ({placeholders}))",
}


def fetch_row_count(
    conn: sqlite3.Connection,
    table: str,
    column_name: str,
    ids: tuple[object, ...],
) -> int:
    placeholders = in_placeholders(ids)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE {column_name} IN ({placeholders})",
        ids,
    ).fetchone()
    if row is None:
        return 0
    n = row["n"]
    if not isinstance(n, int):
        raise ValueError(f"Unexpected non-integer count from table '{table}'.")
    return n


def count_child_rows_for_account_ids(
    conn: sqlite3.Connection,
    table: str,
    account_ids: tuple[int, ...],
) -> int:
    predicate = _CHILD_COUNT_PREDICATES[table].format(placeholders=in_placeholders(account_ids))
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {predicate}", account_ids).fetchone()
    return int(row["n"]) if row is not None else 0
