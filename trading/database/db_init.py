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

_LEGACY_TEST_SHADOW_KIND = "test_shadow"
_CANONICAL_MANUAL_ONLY_KIND = "manual_only"
_LEGACY_TEST_ACCOUNT_NAME = "test_account_bt"
_CANONICAL_TEST_ACCOUNT_NAME = "test_account"
_ACCOUNT_ID_REFERENCE_TABLES = (
    "trades",
    "equity_snapshots",
    "backtest_runs",
    "rotation_episodes",
    "broker_orders",
    "walk_forward_groups",
    "promotion_reviews",
)


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


def _backfill_manual_only_account_kind(conn: DBConnection) -> None:
    if "account_kind" not in _column_names(conn, "accounts"):
        return
    columns = _column_names(conn, "accounts")
    has_live_trading_enabled = "live_trading_enabled" in columns
    if has_live_trading_enabled:
        conn.execute(
            "UPDATE accounts "
            "SET account_kind = ?, live_trading_enabled = 0 "
            "WHERE account_kind = ?",
            (_CANONICAL_MANUAL_ONLY_KIND, _LEGACY_TEST_SHADOW_KIND),
        )
    else:
        conn.execute(
            "UPDATE accounts SET account_kind = ? WHERE account_kind = ?",
            (_CANONICAL_MANUAL_ONLY_KIND, _LEGACY_TEST_SHADOW_KIND),
        )
    conn.commit()


def _account_row_id(conn: DBConnection, account_name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM accounts WHERE name = ?",
        (account_name,),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def _table_exists(conn: DBConnection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _merge_legacy_test_account_rows(conn: DBConnection) -> None:
    if "name" not in _column_names(conn, "accounts"):
        return

    legacy_id = _account_row_id(conn, _LEGACY_TEST_ACCOUNT_NAME)
    if legacy_id is None:
        return

    canonical_id = _account_row_id(conn, _CANONICAL_TEST_ACCOUNT_NAME)
    if canonical_id is None:
        conn.execute(
            "UPDATE accounts SET name = ?, account_kind = ?, live_trading_enabled = 0 WHERE id = ?",
            (_CANONICAL_TEST_ACCOUNT_NAME, _CANONICAL_MANUAL_ONLY_KIND, legacy_id),
        )
        conn.commit()
        return

    for table_name in _ACCOUNT_ID_REFERENCE_TABLES:
        if not _table_exists(conn, table_name):
            continue
        conn.execute(
            f"UPDATE {table_name} SET account_id = ? WHERE account_id = ?",
            (canonical_id, legacy_id),
        )

    conn.execute(
        "DELETE FROM accounts WHERE id = ?",
        (legacy_id,),
    )
    conn.execute(
        "UPDATE accounts SET account_kind = ?, live_trading_enabled = 0 WHERE id = ?",
        (_CANONICAL_MANUAL_ONLY_KIND, canonical_id),
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
    _backfill_manual_only_account_kind(conn)
    _merge_legacy_test_account_rows(conn)
    conn.commit()
