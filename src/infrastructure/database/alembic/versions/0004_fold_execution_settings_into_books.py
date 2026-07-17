"""Fold execution settings into books; drop the 1:1 table and account columns.

Revision ID: 0004
Revises: 0003

Execution settings are book-owned (database-cleanup-roadmap item A2, decided
2026-07-16): the ten execution knobs become columns on books, replacing both
the unread book_execution_settings 1:1 table and the nine legacy account
execution columns that live execution still read. Backfill order per book:
its book_execution_settings row when present, else the parent account's
values, else DDL defaults — so every book's effective settings are unchanged.

Self-contained by convention: no application imports, literal DDL only.
Column adds use ALTER TABLE ADD COLUMN (SQLite supports CHECK + constant
DEFAULT there); the column drops are explicit table rebuilds.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Execution columns added to books — DDL mirrors the book_execution_settings
# table from revision 0001.
_BOOK_EXECUTION_COLUMN_DDL = (
    "learning_enabled INTEGER NOT NULL DEFAULT 0 CHECK (learning_enabled IN (0, 1))",
    (
        "risk_policy TEXT NOT NULL DEFAULT 'none' CHECK ("
        "risk_policy IN ('none', 'fixed_stop', 'take_profit', 'stop_and_target'))"
    ),
    "stop_loss_pct REAL",
    "take_profit_pct REAL",
    "profit_take_pct REAL",
    "max_loss_pct REAL",
    "trade_size_pct REAL",
    "max_position_pct REAL",
    "max_trades_per_run INTEGER CHECK (max_trades_per_run IS NULL OR max_trades_per_run >= 1)",
    "instrument_mode TEXT NOT NULL DEFAULT 'equity' CHECK (instrument_mode IN ('equity', 'leaps'))",
)

_EXECUTION_COLUMNS = (
    "learning_enabled",
    "risk_policy",
    "stop_loss_pct",
    "take_profit_pct",
    "profit_take_pct",
    "max_loss_pct",
    "trade_size_pct",
    "max_position_pct",
    "max_trades_per_run",
    "instrument_mode",
)

# accounts columns dropped by this revision (max_trades_per_run never existed
# on accounts).
_DROPPED_ACCOUNT_COLUMNS = (
    "learning_enabled",
    "risk_policy",
    "stop_loss_pct",
    "take_profit_pct",
    "trade_size_pct",
    "max_position_pct",
    "instrument_mode",
    "profit_take_pct",
    "max_loss_pct",
)

# Explicit copy lists — rebuilds must never use SELECT *.
_KEPT_ACCOUNT_COLUMNS = (
    "id",
    "name",
    "account_kind",
    "strategy",
    "base_ccy",
    "initial_cash",
    "created_at",
    "updated_at",
    "benchmark_ticker",
    "descriptive_name",
    "goal_min_return_pct",
    "goal_max_return_pct",
    "goal_period",
    "option_strike_offset_pct",
    "option_min_dte",
    "option_max_dte",
    "option_type",
    "target_delta_min",
    "target_delta_max",
    "max_premium_per_trade",
    "max_contracts_per_trade",
    "iv_rank_min",
    "iv_rank_max",
    "roll_dte_threshold",
    "trade_universes",
    "broker_type",
    "broker_host",
    "broker_port",
    "broker_client_id",
    "live_trading_enabled",
)

_BOOK_BASE_COLUMNS = (
    "id",
    "account_id",
    "name",
    "status",
    "is_default",
    "start_equity",
    "current_cash",
    "current_equity",
    "trade_universes",
    "goal_min_return_pct",
    "goal_max_return_pct",
    "goal_period",
    "created_at",
    "updated_at",
)

_ACCOUNTS_DDL_TEMPLATE = """
    CREATE TABLE accounts_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        account_kind TEXT NOT NULL DEFAULT 'managed',
        strategy TEXT NOT NULL,
        base_ccy TEXT NOT NULL DEFAULT 'USD',
        initial_cash REAL NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        benchmark_ticker TEXT NOT NULL DEFAULT 'SPY',
        descriptive_name TEXT NOT NULL DEFAULT '',
        goal_min_return_pct REAL,
        goal_max_return_pct REAL,
        goal_period TEXT NOT NULL DEFAULT 'monthly',{execution_block}
        option_strike_offset_pct REAL,
        option_min_dte INTEGER,
        option_max_dte INTEGER,
        option_type TEXT,
        target_delta_min REAL,
        target_delta_max REAL,
        max_premium_per_trade REAL,
        max_contracts_per_trade INTEGER,
        iv_rank_min REAL,
        iv_rank_max REAL,
        roll_dte_threshold INTEGER,{profit_block}
        trade_universes TEXT,
        broker_type TEXT NOT NULL DEFAULT 'paper',
        broker_host TEXT,
        broker_port INTEGER,
        broker_client_id INTEGER,
        live_trading_enabled INTEGER NOT NULL DEFAULT 0
    )
"""

# The 0003 shape splits the execution columns around the option block.
_ACCOUNTS_EXECUTION_BLOCK = """
        learning_enabled INTEGER NOT NULL DEFAULT 0,
        risk_policy TEXT NOT NULL DEFAULT 'none',
        stop_loss_pct REAL,
        take_profit_pct REAL,
        trade_size_pct REAL,
        max_position_pct REAL,
        instrument_mode TEXT NOT NULL DEFAULT 'equity',"""
_ACCOUNTS_PROFIT_BLOCK = """
        profit_take_pct REAL,
        max_loss_pct REAL,"""

_BOOKS_DDL_BASE = """
    CREATE TABLE books_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
        is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
        start_equity REAL NOT NULL,
        current_cash REAL NOT NULL,
        current_equity REAL NOT NULL,
        trade_universes TEXT,
        goal_min_return_pct REAL,
        goal_max_return_pct REAL,
        goal_period TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        UNIQUE (account_id, name)
    )
"""

_BOOKS_INDEXES = (
    "CREATE UNIQUE INDEX idx_books_default_per_account ON books(account_id) WHERE is_default = 1",
    "CREATE INDEX idx_books_account_status ON books(account_id, status)",
)

_BOOK_EXECUTION_SETTINGS_DDL = """
    CREATE TABLE book_execution_settings (
        book_id INTEGER PRIMARY KEY,
        learning_enabled INTEGER NOT NULL DEFAULT 0 CHECK (learning_enabled IN (0, 1)),
        risk_policy TEXT NOT NULL DEFAULT 'none' CHECK (
            risk_policy IN ('none', 'fixed_stop', 'take_profit', 'stop_and_target')
        ),
        stop_loss_pct REAL,
        take_profit_pct REAL,
        profit_take_pct REAL,
        max_loss_pct REAL,
        trade_size_pct REAL,
        max_position_pct REAL,
        max_trades_per_run INTEGER CHECK (max_trades_per_run IS NULL OR max_trades_per_run >= 1),
        instrument_mode TEXT NOT NULL DEFAULT 'equity' CHECK (instrument_mode IN ('equity', 'leaps')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
    )
"""


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0004 rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    for ddl in _BOOK_EXECUTION_COLUMN_DDL:
        op.execute(f"ALTER TABLE books ADD COLUMN {ddl}")

    # Backfill 1: from the book's own settings row where one exists.
    assignments = ", ".join(
        f"{column} = (SELECT s.{column} FROM book_execution_settings s WHERE s.book_id = books.id)"
        for column in _EXECUTION_COLUMNS
    )
    op.execute(
        f"UPDATE books SET {assignments} "
        "WHERE EXISTS (SELECT 1 FROM book_execution_settings s WHERE s.book_id = books.id)"
    )
    # Backfill 2: books without a settings row inherit the parent account's
    # legacy values (max_trades_per_run never existed at account level).
    account_assignments = ", ".join(
        f"{column} = (SELECT a.{column} FROM accounts a WHERE a.id = books.account_id)"
        for column in _DROPPED_ACCOUNT_COLUMNS
    )
    op.execute(
        f"UPDATE books SET {account_assignments} "
        "WHERE NOT EXISTS (SELECT 1 FROM book_execution_settings s WHERE s.book_id = books.id)"
    )

    op.execute("DROP TABLE book_execution_settings")

    # Drop the legacy execution columns from accounts (rebuild).
    column_list = ", ".join(_KEPT_ACCOUNT_COLUMNS)
    op.execute(_ACCOUNTS_DDL_TEMPLATE.format(execution_block="", profit_block=""))
    op.execute(f"INSERT INTO accounts_new ({column_list}) SELECT {column_list} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")
    _check_foreign_keys()


def downgrade() -> None:
    # Restore book_execution_settings from the books columns.
    op.execute(_BOOK_EXECUTION_SETTINGS_DDL)
    execution_list = ", ".join(_EXECUTION_COLUMNS)
    op.execute(
        "INSERT INTO book_execution_settings "
        f"(book_id, {execution_list}, created_at, updated_at) "
        f"SELECT id, {execution_list}, created_at, updated_at FROM books"
    )

    # Rebuild books without the execution columns.
    base_list = ", ".join(_BOOK_BASE_COLUMNS)
    op.execute(_BOOKS_DDL_BASE)
    op.execute(f"INSERT INTO books_new ({base_list}) SELECT {base_list} FROM books")
    op.execute("DROP TABLE books")
    op.execute("ALTER TABLE books_new RENAME TO books")
    for index_sql in _BOOKS_INDEXES:
        op.execute(index_sql)

    # Restore the account execution columns; values return as DDL defaults
    # (the pre-migration backup is the data recovery path).
    kept_list = ", ".join(_KEPT_ACCOUNT_COLUMNS)
    op.execute(
        _ACCOUNTS_DDL_TEMPLATE.format(
            execution_block=_ACCOUNTS_EXECUTION_BLOCK,
            profit_block=_ACCOUNTS_PROFIT_BLOCK,
        )
    )
    op.execute(f"INSERT INTO accounts_new ({kept_list}) SELECT {kept_list} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")
    _check_foreign_keys()
