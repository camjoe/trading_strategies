from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from infrastructure.database.config import get_db_path


class DatabaseBackend(ABC):
    """Abstract interface for database backends.

    Implement this class to swap out SQLite for another database, then
    register your implementation with :func:`set_backend`.

    Opening a connection is the only operation a backend must provide — the
    rest of the codebase uses standard DB-API 2.0 calls (``conn.execute``,
    ``conn.commit``, etc.) directly on the connection object returned by
    :meth:`open_connection`. Schema creation and inspection are not backend
    concerns: the Alembic revision chain owns the schema.
    """

    @abstractmethod
    def open_connection(self) -> Any:
        """Return an open, configured database connection."""


class SQLiteBackend(DatabaseBackend):
    """Concrete backend backed by SQLite via the stdlib ``sqlite3`` module.

    Args:
        db_path: Path to the SQLite file. Omit to resolve it per access.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        # Resolved per access, not pinned in __init__: the default backend is
        # built at import time, which would freeze the path before the
        # environment is set.
        return self._db_path if self._db_path is not None else get_db_path()

    def open_connection(self) -> sqlite3.Connection:
        db_path = self.db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Schema convention: every *_id is a real, enforced FK. SQLite
        # defaults the pragma to OFF per connection.
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets the web backend and runtime jobs read while a writer
        # commits (journal_mode persists in the file; re-asserting is cheap).
        # busy_timeout makes brief lock contention wait instead of raising
        # "database is locked".
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn


_backend: DatabaseBackend = SQLiteBackend()


def get_backend() -> DatabaseBackend:
    """Return the active database backend."""
    return _backend


def set_backend(backend: DatabaseBackend) -> None:
    """Replace the active database backend for the rest of the process.

    Use this to inject a custom backend (e.g. for testing or migration). When
    the replacement should only last for a scope, use :func:`use_backend`.
    """
    global _backend
    _backend = backend


@contextmanager
def use_backend(backend: DatabaseBackend) -> Iterator[DatabaseBackend]:
    """Activate *backend* for the duration of the block, then restore the previous one.

    The scoped form of :func:`set_backend`, for callers that must not leak a
    swapped backend into whatever runs next.
    """
    original = get_backend()
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)
