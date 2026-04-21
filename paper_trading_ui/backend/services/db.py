from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from trading.models import AccountRecord
from trading.database.db_init import ensure_db
from trading.services.accounts_service import (
    get_account,
    get_latest_account_snapshot as fetch_latest_snapshot_row,
)


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


def fetch_account_row(conn: sqlite3.Connection, account_name: str) -> AccountRecord:
    try:
        return get_account(conn, account_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.") from exc
