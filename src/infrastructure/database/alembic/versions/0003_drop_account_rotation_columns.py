"""Rebuild accounts without the 17 retired rotation columns.

Revision ID: 0003
Revises: 0002

Rotation scheduling is book-owned (ADR 014): configuration lives in
book_rotation_settings and rotation state lives in book_strategy_assignments
and rotation_decisions. The account rotation columns have had no readers or
writers since the cutover — AccountRecord stopped materializing them — so this
revision removes them (database-cleanup-roadmap item A1). The pre-migration
backup is the retention path for any historical values.

Self-contained by convention: no application imports, literal DDL only.
SQLite cannot drop columns that fast-path ALTER cannot express safely across
versions, so both directions are explicit table rebuilds (create new -> copy
-> drop -> rename). The downgrade restores the 0001 column shape; dropped
rotation values come back as their DDL defaults, not their old data.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Frozen from revision 0001; deployed databases may carry a different frozen
# literal in this DEFAULT, and the schema comparator ignores its value.
_ROTATION_OVERLAY_WATCHLIST_DEFAULT = (
    '["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","JNJ","UNH","XOM","WMT"]'
)

# Explicit copy list (the 39 kept columns) — rebuilds must never use SELECT *.
_KEPT_COLUMNS = (
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
    "learning_enabled",
    "risk_policy",
    "stop_loss_pct",
    "take_profit_pct",
    "trade_size_pct",
    "max_position_pct",
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
    "profit_take_pct",
    "max_loss_pct",
    "trade_universes",
    "broker_type",
    "broker_host",
    "broker_port",
    "broker_client_id",
    "live_trading_enabled",
)

# Kept-column DDL, verbatim from revision 0001 minus the rotation block.
# The rotation block is interpolated between max_loss_pct and trade_universes
# on downgrade so the restored table matches the 0001 shape exactly.
_TABLE_DDL_TEMPLATE = """
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
        goal_period TEXT NOT NULL DEFAULT 'monthly',
        learning_enabled INTEGER NOT NULL DEFAULT 0,
        risk_policy TEXT NOT NULL DEFAULT 'none',
        stop_loss_pct REAL,
        take_profit_pct REAL,
        trade_size_pct REAL,
        max_position_pct REAL,
        instrument_mode TEXT NOT NULL DEFAULT 'equity',
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
        roll_dte_threshold INTEGER,
        profit_take_pct REAL,
        max_loss_pct REAL,{rotation_block}
        trade_universes TEXT,
        broker_type TEXT NOT NULL DEFAULT 'paper',
        broker_host TEXT,
        broker_port INTEGER,
        broker_client_id INTEGER,
        live_trading_enabled INTEGER NOT NULL DEFAULT 0
    )
"""

_ROTATION_BLOCK = f"""
        rotation_enabled INTEGER NOT NULL DEFAULT 0,
        rotation_mode TEXT NOT NULL DEFAULT 'time',
        rotation_optimality_mode TEXT NOT NULL DEFAULT 'previous_period_best',
        rotation_interval_days INTEGER,
        rotation_interval_minutes INTEGER,
        rotation_lookback_days INTEGER,
        rotation_schedule TEXT,
        rotation_regime_strategy_risk_on TEXT,
        rotation_regime_strategy_neutral TEXT,
        rotation_regime_strategy_risk_off TEXT,
        rotation_overlay_mode TEXT NOT NULL DEFAULT 'none',
        rotation_overlay_min_tickers INTEGER,
        rotation_overlay_confidence_threshold REAL,
        rotation_overlay_watchlist TEXT NOT NULL DEFAULT '{_ROTATION_OVERLAY_WATCHLIST_DEFAULT}',
        rotation_active_index INTEGER NOT NULL DEFAULT 0,
        rotation_last_at TEXT,
        rotation_active_strategy TEXT,"""


def _rebuild(*, with_rotation_columns: bool) -> None:
    column_list = ", ".join(_KEPT_COLUMNS)
    rotation_block = _ROTATION_BLOCK if with_rotation_columns else ""
    op.execute(_TABLE_DDL_TEMPLATE.format(rotation_block=rotation_block))
    op.execute(f"INSERT INTO accounts_new ({column_list}) SELECT {column_list} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")
    # Children (books, orders, trades, ...) reference accounts, so check the
    # whole database, not just the rebuilt table.
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"accounts rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    _rebuild(with_rotation_columns=False)


def downgrade() -> None:
    # Restores the 0001 column shape; rotation values return as DDL defaults
    # (the pre-migration backup is the data recovery path).
    _rebuild(with_rotation_columns=True)
