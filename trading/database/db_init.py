from typing import Any

from trading.database.db_backend import get_backend
from trading.database.db_migrations import (
    ACCOUNT_BROKER_MIGRATIONS,
    ACCOUNT_MIGRATIONS,
    BACKTEST_RUN_MIGRATIONS,
    ColumnMigration,
    GLOBAL_SETTINGS_MIGRATIONS,
    ORDER_FILL_MIGRATIONS,
)
from trading.database.db_schema import SCHEMA_SQL

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any

_LEGACY_MANUAL_ONLY_KIND = "manual_only"
_CANONICAL_MANAGED_KIND = "managed"


def ensure_db() -> DBConnection:
    conn = get_backend().open_connection()
    init_schema(conn)
    return conn


def _column_names(conn: DBConnection, table_name: str) -> set[str]:
    return get_backend().get_table_columns(conn, table_name)


def _ensure_column(conn: DBConnection, table_name: str, migration: ColumnMigration) -> None:
    if migration.column_name in _column_names(conn, table_name):
        return
    conn.execute(migration.ddl)
    for stmt in migration.post_sql:
        conn.execute(stmt)
    conn.commit()


def _backfill_removed_manual_only_kind(conn: DBConnection) -> None:
    if "account_kind" not in _column_names(conn, "accounts"):
        return
    conn.execute(
        "UPDATE accounts SET account_kind = ? WHERE account_kind = ?",
        (_CANONICAL_MANAGED_KIND, _LEGACY_MANUAL_ONLY_KIND),
    )
    conn.commit()


def init_schema(conn: DBConnection) -> None:
    get_backend().run_script(conn, SCHEMA_SQL)
    for migration in ACCOUNT_MIGRATIONS:
        _ensure_column(conn, "accounts", migration)
    for migration in BACKTEST_RUN_MIGRATIONS:
        _ensure_column(conn, "backtest_runs", migration)
    for migration in ACCOUNT_BROKER_MIGRATIONS:
        _ensure_column(conn, "accounts", migration)
    for migration in ORDER_FILL_MIGRATIONS:
        _ensure_column(conn, "order_fills", migration)
    for migration in GLOBAL_SETTINGS_MIGRATIONS:
        _ensure_column(conn, "global_settings", migration)
    _backfill_removed_manual_only_kind(conn)
    conn.commit()
