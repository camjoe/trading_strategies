from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from trading.database.db_init import ensure_db


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()
