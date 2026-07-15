from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from infrastructure.database.backend import get_backend
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION, read_database_revisions

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any

_SETUP_COMMAND = "python -m scripts.data_ops.setup_db_schema"
_BASELINE_COMMAND = "python -m scripts.data_ops.manage_db_migrations baseline"
_STATUS_COMMAND = "python -m scripts.data_ops.manage_db_migrations status"


class SchemaVersionError(RuntimeError):
    """The connected database is not at the expected schema revision.

    Raised by ``ensure_db()`` before any application query runs. Runtime
    never applies or downgrades migrations; the message carries the exact
    operator command that remediates the state.
    """


def _application_table_count(conn: DBConnection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
    ).fetchone()
    return int(row[0])


def _schema_version_error(conn: DBConnection) -> str | None:
    """Return the failure message for a connection, or None when at head."""
    revisions = read_database_revisions(conn)
    if revisions == (EXPECTED_HEAD_REVISION,):
        return None
    if not revisions:
        if _application_table_count(conn) == 0:
            return f"Database is missing or empty. Create the schema with: {_SETUP_COMMAND}"
        return f"Database is populated but has no Alembic revision. Adopt it with: {_BASELINE_COMMAND}"
    if len(revisions) > 1:
        return (
            f"Database has a branched revision history ({', '.join(revisions)}). "
            f"Restore from backup and investigate; inspect with: {_STATUS_COMMAND}"
        )
    return (
        f"Database revision {revisions[0]} does not match the expected head "
        f"{EXPECTED_HEAD_REVISION}. Inspect and migrate with: {_STATUS_COMMAND}"
    )


def ensure_db() -> DBConnection:
    """Open a connection and verify the database is at the expected head.

    Verification is plain SQL against ``alembic_version`` — runtime never
    imports Alembic and never mutates the schema. Missing, unversioned,
    outdated, newer, or branched databases raise ``SchemaVersionError`` with
    the remediation command before any application query runs.
    """
    conn = get_backend().open_connection()
    try:
        message = _schema_version_error(conn)
    except Exception:
        conn.close()
        raise
    if message is not None:
        conn.close()
        raise SchemaVersionError(message)
    return conn


@contextmanager
def db_session() -> Iterator[DBConnection]:
    """Open a verified DB connection and guarantee it is closed.

    The shared resource-lifecycle wrapper for the `conn = ensure_db(); try: ...
    finally: conn.close()` pattern. Tests stub the connection by patching
    `infrastructure.database.init.ensure_db`.
    """
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()
