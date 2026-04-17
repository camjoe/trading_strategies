"""Stable public facade for trading DB schema and migration helpers.

External callers should keep importing from ``trading.database.db``.
The sibling ``db_*`` modules own the internal split for schema DDL, migration
definitions, and schema-initialization helpers.
"""

from trading.database.db_common import (
    DB_PATH,
    DBConnection,
    DEFAULT_ROTATION_OVERLAY_WATCHLIST,
    DEFAULT_ROTATION_OVERLAY_WATCHLIST_FILE,
    DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON,
)
from trading.database.db_init import _column_names, _ensure_column, ensure_db, init_schema
from trading.database.db_migrations import (
    ACCOUNT_BROKER_MIGRATIONS,
    ACCOUNT_MIGRATIONS,
    BACKTEST_RUN_MIGRATIONS,
    ORDER_FILL_MIGRATIONS,
    ColumnMigration,
    GLOBAL_SETTINGS_MIGRATIONS,
)
from trading.database.db_schema import ACCOUNTS_TABLE_SQL, SCHEMA_SQL

__all__ = [
    "ACCOUNT_BROKER_MIGRATIONS",
    "ACCOUNT_MIGRATIONS",
    "ACCOUNTS_TABLE_SQL",
    "BACKTEST_RUN_MIGRATIONS",
    "ColumnMigration",
    "DB_PATH",
    "DBConnection",
    "DEFAULT_ROTATION_OVERLAY_WATCHLIST",
    "DEFAULT_ROTATION_OVERLAY_WATCHLIST_FILE",
    "DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON",
    "GLOBAL_SETTINGS_MIGRATIONS",
    "ORDER_FILL_MIGRATIONS",
    "SCHEMA_SQL",
    "_column_names",
    "_ensure_column",
    "ensure_db",
    "init_schema",
]
