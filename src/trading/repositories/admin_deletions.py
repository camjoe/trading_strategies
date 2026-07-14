from __future__ import annotations

import sqlite3

from infrastructure.database.sql_helpers import in_placeholders


def _fetch_ids_by_account_ids(
    conn: sqlite3.Connection,
    *,
    table: str,
    account_ids: tuple[int, ...],
) -> tuple[int, ...]:
    placeholders = in_placeholders(account_ids)
    rows = conn.execute(
        f"SELECT id FROM {table} WHERE account_id IN ({placeholders})",
        account_ids,
    ).fetchall()
    ids = tuple(int(row["id"]) for row in rows)
    if len(ids) != len(rows):
        raise ValueError(f"Unexpected non-integer id returned from table '{table}'.")
    return ids


def _delete_by_ids(
    conn: sqlite3.Connection,
    *,
    table: str,
    column_name: str,
    ids: tuple[int, ...],
) -> None:
    placeholders = in_placeholders(ids)
    conn.execute(f"DELETE FROM {table} WHERE {column_name} IN ({placeholders})", ids)


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


def fetch_backtest_run_ids_for_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> tuple[int, ...]:
    return _fetch_ids_by_account_ids(conn, table="backtest_runs", account_ids=account_ids)


def fetch_promotion_review_ids_for_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> tuple[int, ...]:
    return _fetch_ids_by_account_ids(conn, table="promotion_reviews", account_ids=account_ids)


def fetch_walk_forward_group_ids_for_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> tuple[int, ...]:
    return _fetch_ids_by_account_ids(conn, table="walk_forward_groups", account_ids=account_ids)


def delete_backtest_equity_snapshots_by_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="backtest_equity_snapshots", column_name="run_id", ids=run_ids)


def delete_backtest_trades_by_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="backtest_trades", column_name="run_id", ids=run_ids)


def delete_backtest_runs_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="backtest_runs", column_name="account_id", ids=account_ids)


def delete_promotion_review_events_by_review_ids(
    conn: sqlite3.Connection,
    review_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="promotion_review_events", column_name="review_id", ids=review_ids)


def delete_promotion_reviews_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="promotion_reviews", column_name="account_id", ids=account_ids)


def delete_walk_forward_group_runs_by_group_ids(
    conn: sqlite3.Connection,
    group_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="walk_forward_group_runs", column_name="group_id", ids=group_ids)


def delete_walk_forward_groups_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="walk_forward_groups", column_name="account_id", ids=account_ids)


def count_equity_snapshots_for_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> int:
    # Snapshots are book-keyed; count through the account's books.
    placeholders = in_placeholders(account_ids)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM equity_snapshots WHERE book_id IN "
        f"(SELECT id FROM books WHERE account_id IN ({placeholders}))",
        account_ids,
    ).fetchone()
    return int(row["n"]) if row is not None else 0


def delete_equity_snapshots_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    # Snapshots are book-keyed; delete through the account's books.
    placeholders = in_placeholders(account_ids)
    conn.execute(
        f"DELETE FROM equity_snapshots WHERE book_id IN (SELECT id FROM books WHERE account_id IN ({placeholders}))",
        account_ids,
    )


def delete_trades_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="trades", column_name="account_id", ids=account_ids)


def delete_accounts_by_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="accounts", column_name="id", ids=account_ids)
