"""Final accounts shrink; required book universes with change history.

Revision ID: 0008
Revises: 0007

Closes database-cleanup-roadmap items A4/A5/A7 (decided 2026-07-16):

- ``book_universe_history`` records which universes a book traded, when
  (append-only, mirroring the book_strategy_assignments idiom), so
  evaluation can call out cross-universe comparisons.
- ``books.trade_universes`` becomes NOT NULL — books are always explicitly
  set. Backfill: the book's own value, else the parent account's, else the
  literal ``'["default"]'`` (the ``default`` universe file ships with the
  repo, frozen from the global ticker list).
- ``accounts`` drops its last legacy columns — ``strategy`` (truth is
  book_strategy_assignments), the three goal columns and
  ``trade_universes`` (book-owned) — reaching its target shape: identity,
  custody, and broker connection.

Self-contained by convention: no application imports, literal DDL only.
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_DEFAULT_UNIVERSES_LITERAL = '["default"]'

_UNIVERSE_HISTORY_DDL = """
    CREATE TABLE book_universe_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        universes_json TEXT NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
    )
"""

_UNIVERSE_HISTORY_INDEXES = (
    "CREATE INDEX idx_book_universe_history_book_from ON book_universe_history(book_id, effective_from DESC)",
    (
        "CREATE UNIQUE INDEX idx_book_universe_history_open_per_book "
        "ON book_universe_history(book_id) WHERE effective_to IS NULL"
    ),
)

# Books copy list for the NOT NULL rebuild (the full 0005 shape).
_BOOK_COLUMNS = (
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
)

_BOOKS_DDL_TEMPLATE = """
    CREATE TABLE books_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
        is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
        start_equity REAL NOT NULL,
        current_cash REAL NOT NULL,
        current_equity REAL NOT NULL,
        trade_universes TEXT{universes_constraint},
        goal_min_return_pct REAL,
        goal_max_return_pct REAL,
        goal_period TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
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
        option_strike_offset_pct REAL,
        option_min_dte INTEGER,
        option_max_dte INTEGER,
        option_type TEXT CHECK (option_type IS NULL OR option_type IN ('call', 'put', 'both')),
        target_delta_min REAL,
        target_delta_max REAL,
        max_premium_per_trade REAL,
        max_contracts_per_trade INTEGER,
        iv_rank_min REAL,
        iv_rank_max REAL,
        roll_dte_threshold INTEGER,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        UNIQUE (account_id, name)
    )
"""

_BOOKS_INDEXES = (
    "CREATE UNIQUE INDEX idx_books_default_per_account ON books(account_id) WHERE is_default = 1",
    "CREATE INDEX idx_books_account_status ON books(account_id, status)",
)

# accounts copy lists: the final 14-column shape, and the 0007 shape restored
# by the downgrade.
_FINAL_ACCOUNT_COLUMNS = (
    "id",
    "name",
    "account_kind",
    "base_ccy",
    "initial_cash",
    "created_at",
    "updated_at",
    "benchmark_ticker",
    "descriptive_name",
    "broker_type",
    "broker_host",
    "broker_port",
    "broker_client_id",
    "live_trading_enabled",
)

_ACCOUNTS_DDL_TEMPLATE = """
    CREATE TABLE accounts_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        account_kind TEXT NOT NULL DEFAULT 'managed',{legacy_block}
        base_ccy TEXT NOT NULL DEFAULT 'USD',
        initial_cash REAL NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        benchmark_ticker TEXT NOT NULL DEFAULT 'SPY',
        descriptive_name TEXT NOT NULL DEFAULT '',
        broker_type TEXT NOT NULL DEFAULT 'paper',
        broker_host TEXT,
        broker_port INTEGER,
        broker_client_id INTEGER,
        live_trading_enabled INTEGER NOT NULL DEFAULT 0
    )
"""

# The 0007 legacy columns restored (as defaults) by the downgrade. strategy is
# NOT NULL in the old shape; restore it as the empty string.
_ACCOUNTS_LEGACY_BLOCK = """
        strategy TEXT NOT NULL DEFAULT '',
        goal_min_return_pct REAL,
        goal_max_return_pct REAL,
        goal_period TEXT NOT NULL DEFAULT 'monthly',
        trade_universes TEXT,"""


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0008 rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    op.execute(_UNIVERSE_HISTORY_DDL)
    for index_sql in _UNIVERSE_HISTORY_INDEXES:
        op.execute(index_sql)

    # Backfill: book value -> parent account's value -> the default universe.
    op.execute(
        """
        UPDATE books
        SET trade_universes = (SELECT a.trade_universes FROM accounts a WHERE a.id = books.account_id)
        WHERE trade_universes IS NULL
        """
    )
    op.execute(f"UPDATE books SET trade_universes = '{_DEFAULT_UNIVERSES_LITERAL}' WHERE trade_universes IS NULL")

    # Rebuild books with trade_universes NOT NULL.
    book_list = ", ".join(_BOOK_COLUMNS)
    op.execute(_BOOKS_DDL_TEMPLATE.format(universes_constraint=" NOT NULL"))
    op.execute(f"INSERT INTO books_new ({book_list}) SELECT {book_list} FROM books")
    op.execute("DROP TABLE books")
    op.execute("ALTER TABLE books_new RENAME TO books")
    for index_sql in _BOOKS_INDEXES:
        op.execute(index_sql)

    # Seed one open history row per book so "which universes, when" is
    # answerable from day one.
    op.execute(
        """
        INSERT INTO book_universe_history (book_id, universes_json, effective_from, effective_to)
        SELECT id, trade_universes, updated_at, NULL FROM books
        """
    )

    # Drop the last legacy account columns (final 14-column shape).
    account_list = ", ".join(_FINAL_ACCOUNT_COLUMNS)
    op.execute(_ACCOUNTS_DDL_TEMPLATE.format(legacy_block=""))
    op.execute(f"INSERT INTO accounts_new ({account_list}) SELECT {account_list} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")
    _check_foreign_keys()


def downgrade() -> None:
    # Restore the 0007 accounts shape; legacy values return as DDL defaults
    # (the pre-migration backup is the data recovery path).
    account_list = ", ".join(_FINAL_ACCOUNT_COLUMNS)
    op.execute(_ACCOUNTS_DDL_TEMPLATE.format(legacy_block=_ACCOUNTS_LEGACY_BLOCK))
    op.execute(f"INSERT INTO accounts_new ({account_list}) SELECT {account_list} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")

    # Books: trade_universes returns to nullable (values preserved).
    book_list = ", ".join(_BOOK_COLUMNS)
    op.execute(_BOOKS_DDL_TEMPLATE.format(universes_constraint=""))
    op.execute(f"INSERT INTO books_new ({book_list}) SELECT {book_list} FROM books")
    op.execute("DROP TABLE books")
    op.execute("ALTER TABLE books_new RENAME TO books")
    for index_sql in _BOOKS_INDEXES:
        op.execute(index_sql)

    op.execute("DROP TABLE book_universe_history")
    _check_foreign_keys()
