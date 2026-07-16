from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from infrastructure.database.backend import get_backend
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION, read_database_revisions

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any

_STATUS_COMMAND = "python -m scripts.data_ops.manage_db_migrations status"


class SchemaVersionError(RuntimeError):
    """The connected database is not at the expected schema revision.

    Raised by ``ensure_db()`` before any application query runs. Runtime never
    applies or downgrades migrations; diagnosis and remediation live in the
    operator command named in the message.
    """


def ensure_db() -> DBConnection:
    """Open a connection and verify the database is at the expected head.

    Verification is plain SQL against ``alembic_version`` — runtime never
    imports Alembic and never mutates the schema.
    """
    conn = get_backend().open_connection()
    try:
        revisions = read_database_revisions(conn)
    except Exception:
        conn.close()
        raise
    if revisions != (EXPECTED_HEAD_REVISION,):
        conn.close()
        found = ", ".join(revisions) if revisions else "none"
        raise SchemaVersionError(
            f"Database schema revision is '{found}', expected '{EXPECTED_HEAD_REVISION}'. "
            f"Diagnose and migrate with: {_STATUS_COMMAND}"
        )
    return conn


@contextmanager
def db_session() -> Iterator[DBConnection]:
    """Open a verified DB connection and guarantee it is closed.

    The shared resource-lifecycle wrapper for the `conn = ensure_db(); try: ...
    finally: conn.close()` pattern. Tests stub the connection by patching
    `infrastructure.database.connection.ensure_db`.
    """
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()
