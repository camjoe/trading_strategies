from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from trading.database.db import ensure_db
from trading.repositories.accounts_repository import fetch_account_by_name
from trading.repositories.snapshots_repository import fetch_latest_snapshot_row as fetch_latest_snapshot_row_repo


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


def get_account_row(conn: sqlite3.Connection, account_name: str) -> sqlite3.Row:
    row = fetch_account_by_name(conn, account_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.")
    return row


def get_latest_snapshot_row(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return fetch_latest_snapshot_row_repo(conn, account_id=account_id)
