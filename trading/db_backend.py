from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DatabaseBackend(ABC):
    """Abstract interface for database backends.

    Implement this class to swap out SQLite for another database, then
    register your implementation with :func:`set_backend`.

    Only three operations need to be provided — the rest of the codebase
    uses standard DB-API 2.0 calls (``conn.execute``, ``conn.commit``,
    etc.) directly on the connection object returned by
    :meth:`open_connection`.
    """

    @abstractmethod
    def open_connection(self) -> Any:
        """Return an open, configured database connection."""

    @abstractmethod
    def run_script(self, conn: Any, script: str) -> None:
        """Execute a multi-statement SQL script (e.g. schema creation).

        Equivalent to sqlite3's ``executescript``.  Implementations must
        ensure the script is committed before returning.
        """

    @abstractmethod
    def get_table_columns(self, conn: Any, table: str) -> set[str]:
        """Return the set of column names that currently exist in *table*."""


class SQLiteBackend(DatabaseBackend):
    """Concrete backend backed by SQLite via the stdlib ``sqlite3`` module.

    Args:
        db_path: Path to the SQLite file.  Defaults to the standard
            ``trading/database/paper_trading.db`` location.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path: Path = (
            db_path
            if db_path is not None
            else Path(__file__).resolve().parent / "database" / "paper_trading.db"
        )

    def open_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def run_script(self, conn: Any, script: str) -> None:
        # executescript commits any open transaction before running.
        conn.executescript(script)

    def get_table_columns(self, conn: Any, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}


_backend: DatabaseBackend = SQLiteBackend()


def get_backend() -> DatabaseBackend:
    """Return the active database backend."""
    return _backend


def set_backend(backend: DatabaseBackend) -> None:
    """Replace the active database backend.

    Use this to inject a custom backend (e.g. for testing or migration):

        from trading.db_backend import set_backend, SQLiteBackend
        set_backend(SQLiteBackend(Path("/tmp/test.db")))
    """
    global _backend
    _backend = backend
