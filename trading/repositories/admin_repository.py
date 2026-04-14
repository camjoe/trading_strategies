from __future__ import annotations

import sqlite3


def _in_placeholders(values: tuple[object, ...]) -> str:
    return ",".join(["?"] * len(values))


def _fetch_rows_by_account_ids(
    conn: sqlite3.Connection,
    *,
    table: str,
    account_ids: tuple[int, ...],
) -> list[sqlite3.Row]:
    placeholders = _in_placeholders(account_ids)
    return conn.execute(
        f"SELECT id FROM {table} WHERE account_id IN ({placeholders})",
        account_ids,
    ).fetchall()


def _delete_by_ids(
    conn: sqlite3.Connection,
    *,
    table: str,
    column_name: str,
    ids: tuple[int, ...],
) -> None:
    placeholders = _in_placeholders(ids)
    conn.execute(f"DELETE FROM {table} WHERE {column_name} IN ({placeholders})", ids)


def fetch_all_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, name FROM accounts ORDER BY name ASC").fetchall()


def fetch_accounts_by_names(conn: sqlite3.Connection, names: tuple[str, ...]) -> list[sqlite3.Row]:
    placeholders = _in_placeholders(names)
    return conn.execute(
        f"SELECT id, name FROM accounts WHERE name IN ({placeholders}) ORDER BY name ASC",
        names,
    ).fetchall()


def count_rows(
    conn: sqlite3.Connection,
    table: str,
    where_sql: str,
    params: tuple[object, ...],
) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where_sql}", params).fetchone()
    if row is None:
        return 0
    n = row["n"]
    if not isinstance(n, int):
        raise ValueError(f"Unexpected non-integer count from table '{table}'.")
    return n


def fetch_backtest_run_rows_for_accounts(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> list[sqlite3.Row]:
    return _fetch_rows_by_account_ids(conn, table="backtest_runs", account_ids=account_ids)


def fetch_promotion_review_rows_for_accounts(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> list[sqlite3.Row]:
    return _fetch_rows_by_account_ids(conn, table="promotion_reviews", account_ids=account_ids)


def fetch_walk_forward_group_rows_for_accounts(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> list[sqlite3.Row]:
    return _fetch_rows_by_account_ids(conn, table="walk_forward_groups", account_ids=account_ids)


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


def delete_equity_snapshots_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    _delete_by_ids(conn, table="equity_snapshots", column_name="account_id", ids=account_ids)


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
