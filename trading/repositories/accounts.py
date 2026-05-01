from __future__ import annotations

from collections.abc import Collection
import sqlite3
from dataclasses import astuple

from trading.database.db_backend import get_backend
from trading.database.sql_helpers import in_placeholders
from trading.models import AccountInsert, AccountRecord

_ACCOUNT_INSERT_COLUMNS = (
    "name",
    "account_kind",
    "strategy",
    "initial_cash",
    "created_at",
    "benchmark_ticker",
    "descriptive_name",
    "goal_min_return_pct",
    "goal_max_return_pct",
    "goal_period",
    "learning_enabled",
    "risk_policy",
    "stop_loss_pct",
    "take_profit_pct",
    "trade_size_pct",
    "max_position_pct",
    "instrument_mode",
    "option_strike_offset_pct",
    "option_min_dte",
    "option_max_dte",
    "option_type",
    "target_delta_min",
    "target_delta_max",
    "max_premium_per_trade",
    "max_contracts_per_trade",
    "iv_rank_min",
    "iv_rank_max",
    "roll_dte_threshold",
    "profit_take_pct",
    "max_loss_pct",
)
_ACCOUNT_INSERT_SQL = (
    f"INSERT INTO accounts ({', '.join(_ACCOUNT_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _ACCOUNT_INSERT_COLUMNS)})"
)


def _account_record_from_row(row: sqlite3.Row) -> AccountRecord:
    return AccountRecord.from_mapping(dict(row))


def fetch_account_by_name(conn: sqlite3.Connection, name: str) -> AccountRecord | None:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    return _account_record_from_row(row) if row is not None else None


def insert_account(conn: sqlite3.Connection, account: AccountInsert) -> None:
    conn.execute(_ACCOUNT_INSERT_SQL, astuple(account))
    conn.commit()


def update_account_benchmark(conn: sqlite3.Connection, *, account_id: int, benchmark_ticker: str) -> None:
    conn.execute(
        "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
        (benchmark_ticker, account_id),
    )
    conn.commit()


def fetch_account_listing_rows(conn: sqlite3.Connection) -> list[AccountRecord]:
    return [
        _account_record_from_row(row)
        for row in conn.execute("SELECT * FROM accounts ORDER BY strategy ASC, name ASC").fetchall()
    ]


def fetch_account_rows(
    conn: sqlite3.Connection,
    *,
    account_kinds: Collection[str] | None = None,
) -> list[AccountRecord]:
    if account_kinds is None:
        rows = conn.execute("SELECT * FROM accounts ORDER BY name").fetchall()
        return [_account_record_from_row(row) for row in rows]

    normalized_kinds = tuple(sorted({str(kind) for kind in account_kinds}))
    if not normalized_kinds:
        return []

    rows = conn.execute(
        "SELECT * FROM accounts "
        f"WHERE COALESCE(account_kind, 'managed') IN ({in_placeholders(normalized_kinds)}) "
        "ORDER BY name",
        normalized_kinds,
    ).fetchall()
    return [_account_record_from_row(row) for row in rows]


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


def fetch_all_account_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
    return [str(row["name"]) for row in rows]


# Repository helpers normally require an explicit caller-owned connection.
# This loader is the current exception that supports the service-level
# load_all_account_names() entrypoint for top-level runtime callers.
def _load_all_account_names() -> list[str]:
    conn = get_backend().open_connection()
    try:
        return fetch_all_account_names(conn)
    finally:
        conn.close()


def _load_account_names_by_kinds(account_kinds: Collection[str]) -> list[str]:
    conn = get_backend().open_connection()
    try:
        rows = fetch_account_rows(conn, account_kinds=account_kinds)
        return [row.name for row in rows]
    finally:
        conn.close()
