from trading.database.db_backend import get_backend
from trading.database.db_common import DBConnection
from trading.database.db_migrations import (
    ACCOUNT_BROKER_MIGRATIONS,
    ACCOUNT_MIGRATIONS,
    BACKTEST_RUN_MIGRATIONS,
    ColumnMigration,
    ORDER_FILL_MIGRATIONS,
)
from trading.database.db_schema import SCHEMA_SQL


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
    conn.commit()
