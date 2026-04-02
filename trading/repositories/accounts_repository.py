from __future__ import annotations

import sqlite3

from trading.database.db_backend import DuplicateRecordError, get_backend

__all__ = ["DuplicateRecordError"]

def fetch_account_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()


def insert_account(
    conn: sqlite3.Connection,
    *,
    name: str,
    strategy: str,
    initial_cash: float,
    created_at: str,
    benchmark_ticker: str,
    descriptive_name: str,
    goal_min_return_pct: float | None,
    goal_max_return_pct: float | None,
    goal_period: str,
    learning_enabled: int,
    risk_policy: str,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
    instrument_mode: str,
    option_strike_offset_pct: float | None,
    option_min_dte: int | None,
    option_max_dte: int | None,
    option_type: str | None,
    target_delta_min: float | None,
    target_delta_max: float | None,
    max_premium_per_trade: float | None,
    max_contracts_per_trade: int | None,
    iv_rank_min: float | None,
    iv_rank_max: float | None,
    roll_dte_threshold: int | None,
    profit_take_pct: float | None,
    max_loss_pct: float | None,
) -> None:
    conn.execute(
        """
        INSERT INTO accounts (
            name,
            strategy,
            initial_cash,
            created_at,
            benchmark_ticker,
            descriptive_name,
            goal_min_return_pct,
            goal_max_return_pct,
            goal_period,
            learning_enabled,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
            instrument_mode,
            option_strike_offset_pct,
            option_min_dte,
            option_max_dte,
            option_type,
            target_delta_min,
            target_delta_max,
            max_premium_per_trade,
            max_contracts_per_trade,
            iv_rank_min,
            iv_rank_max,
            roll_dte_threshold,
            profit_take_pct,
            max_loss_pct
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            strategy,
            initial_cash,
            created_at,
            benchmark_ticker,
            descriptive_name,
            goal_min_return_pct,
            goal_max_return_pct,
            goal_period,
            learning_enabled,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
            instrument_mode,
            option_strike_offset_pct,
            option_min_dte,
            option_max_dte,
            option_type,
            target_delta_min,
            target_delta_max,
            max_premium_per_trade,
            max_contracts_per_trade,
            iv_rank_min,
            iv_rank_max,
            roll_dte_threshold,
            profit_take_pct,
            max_loss_pct,
        ),
    )
    conn.commit()


def update_account_benchmark(conn: sqlite3.Connection, *, account_id: int, benchmark_ticker: str) -> None:
    conn.execute(
        "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
        (benchmark_ticker, account_id),
    )
    conn.commit()


def fetch_account_listing_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM accounts ORDER BY strategy ASC, name ASC").fetchall()


def fetch_account_rows_excluding_name(conn: sqlite3.Connection, *, excluded_name: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM accounts WHERE name != ? ORDER BY name",
        (excluded_name,),
    ).fetchall()


def update_account_fields(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    updates: list[str],
    params: list[object],
) -> None:
    query_params = [*params, account_id]
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(query_params))
    conn.commit()


def fetch_all_account_names_from_conn(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
    return [str(row["name"]) for row in rows]


def fetch_all_account_names() -> list[str]:
    conn = get_backend().open_connection()
    try:
        return fetch_all_account_names_from_conn(conn)
    finally:
        conn.close()
