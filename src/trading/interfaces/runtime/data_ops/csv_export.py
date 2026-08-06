from __future__ import annotations

import sqlite3
from pathlib import Path

from infrastructure.database.backend import SQLiteBackend, get_backend
from infrastructure.database.config import get_db_path
from infrastructure.database.connection import verify_schema_revision


def open_db_connection(db_path: Path | None = None) -> tuple[sqlite3.Connection, Path]:
    backend = SQLiteBackend(db_path.resolve()) if db_path is not None else get_backend()
    if db_path is not None:
        resolved_db_path = db_path.resolve()
    elif isinstance(backend, SQLiteBackend):
        resolved_db_path = backend.db_path.resolve()
    else:
        resolved_db_path = get_db_path().resolve()
    if not resolved_db_path.exists():
        raise FileNotFoundError(f"Database file not found: {resolved_db_path}")

    conn = backend.open_connection()
    try:
        verify_schema_revision(conn)
    except Exception:
        conn.close()
        raise
    return conn, resolved_db_path
