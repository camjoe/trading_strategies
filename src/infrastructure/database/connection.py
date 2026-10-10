from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from infrastructure.database.backend import get_backend
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION, read_database_revisions

# Nominally this depends on the active DatabaseBackend, but SQLiteBackend is the
# only implementation. Adding a second one means widening this to a Protocol —
# not back to `Any`, which propagates to every caller and hides mismatches.
DBConnection = sqlite3.Connection

_STATUS_COMMAND = "python -m scripts.data_ops.manage_db_migrations status"


class SchemaVersionError(RuntimeError):
    """The connected database is not at the expected schema revision.

    Raised by ``ensure_db()`` before any application query runs. Runtime never
    applies or downgrades migrations; diagnosis and remediation live in the
    operator command named in the message.
    """


def verify_schema_revision(conn: DBConnection) -> None:
    """Raise ``SchemaVersionError`` unless *conn* is at the expected head.

    Callers that open their own connection from the backend must apply this
    themselves before running application queries; ``ensure_db()`` does it for
    the connection it opens.
    """
    revisions = read_database_revisions(conn)
    if revisions == (EXPECTED_HEAD_REVISION,):
        return
    found = ", ".join(revisions) if revisions else "none"
    raise SchemaVersionError(
        f"Database schema revision is '{found}', expected '{EXPECTED_HEAD_REVISION}'. "
        f"Diagnose and migrate with: {_STATUS_COMMAND}"
    )


def ensure_db() -> DBConnection:
    """Open a connection and verify the database is at the expected head."""
    conn = get_backend().open_connection()
    try:
        verify_schema_revision(conn)
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def db_session() -> Generator[DBConnection]:
    """Open a verified DB connection and guarantee it is closed.

    Tests stub the connection by patching
    ``infrastructure.database.connection.ensure_db``.
    """
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()
