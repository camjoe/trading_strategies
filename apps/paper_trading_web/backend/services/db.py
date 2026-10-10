from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from infrastructure.database.connection import ensure_db


@contextmanager
def db_conn() -> Generator[sqlite3.Connection]:
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()
