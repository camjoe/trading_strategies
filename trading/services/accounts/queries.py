from __future__ import annotations

import sqlite3

from trading.database.db_backend import get_backend
from trading.models import AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.snapshots import (
    fetch_latest_snapshot_row,
    fetch_snapshot_history_rows,
)


def _normalize_account_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("account_name cannot be empty.")
    return normalized


def _require_positive_account_id(account_id: int) -> None:
    if account_id <= 0:
        raise ValueError("account_id must be positive.")


def find_account(conn: sqlite3.Connection, name: str) -> AccountRecord | None:
    return AccountRepository(conn).fetch_by_name(_normalize_account_name(name))


def list_account_records(conn: sqlite3.Connection) -> list[AccountRecord]:
    return AccountRepository(conn).fetch_all()


def list_account_names(conn: sqlite3.Connection) -> list[str]:
    return AccountRepository(conn).fetch_names()


def get_latest_account_snapshot(
    conn: sqlite3.Connection,
    account_id: int,
) -> dict[str, object] | None:
    _require_positive_account_id(account_id)
    return fetch_latest_snapshot_row(conn, account_id=account_id)


def list_account_snapshots(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    limit: int,
) -> list[dict[str, object]]:
    _require_positive_account_id(account_id)
    if limit <= 0:
        raise ValueError("limit must be positive.")
    return fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def load_runtime_eligible_account_names() -> list[str]:
    conn = get_backend().open_connection()
    try:
        return AccountRepository(conn).fetch_names()
    finally:
        conn.close()
