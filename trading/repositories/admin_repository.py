from __future__ import annotations

import sqlite3


def fetch_all_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, name FROM accounts ORDER BY name ASC").fetchall()


def fetch_accounts_by_names(conn: sqlite3.Connection, names: tuple[str, ...]) -> list[sqlite3.Row]:
    placeholders = ",".join(["?"] * len(names))
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
    placeholders = ",".join(["?"] * len(account_ids))
    return conn.execute(
        f"SELECT id FROM backtest_runs WHERE account_id IN ({placeholders})",
        account_ids,
    ).fetchall()


def delete_backtest_equity_snapshots_by_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
) -> None:
    placeholders = ",".join(["?"] * len(run_ids))
    conn.execute(f"DELETE FROM backtest_equity_snapshots WHERE run_id IN ({placeholders})", run_ids)


def delete_backtest_trades_by_run_ids(
    conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
) -> None:
    placeholders = ",".join(["?"] * len(run_ids))
    conn.execute(f"DELETE FROM backtest_trades WHERE run_id IN ({placeholders})", run_ids)


def delete_backtest_runs_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    placeholders = ",".join(["?"] * len(account_ids))
    conn.execute(f"DELETE FROM backtest_runs WHERE account_id IN ({placeholders})", account_ids)


def delete_equity_snapshots_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    placeholders = ",".join(["?"] * len(account_ids))
    conn.execute(f"DELETE FROM equity_snapshots WHERE account_id IN ({placeholders})", account_ids)


def delete_trades_by_account_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    placeholders = ",".join(["?"] * len(account_ids))
    conn.execute(f"DELETE FROM trades WHERE account_id IN ({placeholders})", account_ids)


def delete_accounts_by_ids(
    conn: sqlite3.Connection,
    account_ids: tuple[int, ...],
) -> None:
    placeholders = ",".join(["?"] * len(account_ids))
    conn.execute(f"DELETE FROM accounts WHERE id IN ({placeholders})", account_ids)
