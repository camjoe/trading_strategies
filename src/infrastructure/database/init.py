from __future__ import annotations
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from infrastructure.database.backend import get_backend
from infrastructure.database.migrations import (
    ACCOUNT_BROKER_MIGRATIONS,
    ACCOUNT_MIGRATIONS,
    BACKTEST_RUN_MIGRATIONS,
    BOOK_MIGRATIONS_BY_TABLE,
    ColumnMigration,
    GLOBAL_SETTINGS_MIGRATIONS,
    TABLE_MIGRATIONS_BY_TABLE,
)
from infrastructure.database.schema import SCHEMA_SQL

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any


def ensure_db() -> DBConnection:
    conn = get_backend().open_connection()
    init_schema(conn)
    return conn


@contextmanager
def db_session() -> Iterator[DBConnection]:
    """Open an initialized DB connection and guarantee it is closed.

    The shared resource-lifecycle wrapper for the `conn = ensure_db(); try: ...
    finally: conn.close()` pattern. Tests stub the connection by patching
    `infrastructure.database.init.ensure_db`.
    """
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


def _column_names(conn: DBConnection, table_name: str) -> set[str]:
    return get_backend().get_table_columns(conn, table_name)


def _ensure_column(conn: DBConnection, table_name: str, migration: ColumnMigration) -> None:
    if migration.column_name in _column_names(conn, table_name):
        return
    conn.execute(migration.ddl)
    for stmt in migration.post_sql:
        conn.execute(stmt)
    conn.commit()


def init_schema(conn: DBConnection) -> None:
    get_backend().run_script(conn, SCHEMA_SQL)
    for migration in ACCOUNT_MIGRATIONS:
        _ensure_column(conn, "accounts", migration)
    for migration in BACKTEST_RUN_MIGRATIONS:
        _ensure_column(conn, "backtest_runs", migration)
    for migration in ACCOUNT_BROKER_MIGRATIONS:
        _ensure_column(conn, "accounts", migration)
    for migration in GLOBAL_SETTINGS_MIGRATIONS:
        _ensure_column(conn, "global_settings", migration)
    for table_name, migrations in TABLE_MIGRATIONS_BY_TABLE.items():
        for migration in migrations:
            _ensure_column(conn, table_name, migration)
    for table_name, migrations in BOOK_MIGRATIONS_BY_TABLE.items():
        for migration in migrations:
            _ensure_column(conn, table_name, migration)
    conn.commit()
