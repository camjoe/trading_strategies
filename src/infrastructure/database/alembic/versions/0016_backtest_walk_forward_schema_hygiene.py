"""Program A schema hygiene for the backtest and walk-forward tables.

Revision ID: 0016
Revises: 0015

Puts the five research tables "in good shape" (docs/reference/
research-persistence-review.md):

- rename ``backtest_trades`` -> ``backtest_executions`` and its ``trade_time``
  -> ``execution_date`` (each row is one simulated buy/sell on a daily bar, not
  a round-trip trade);
- rename ``backtest_equity_snapshots.snapshot_time`` -> ``snapshot_date``
  (daily resolution). The identically named ``equity_snapshots`` and
  ``risk_snapshots`` columns belong to other tables and are left untouched;
- rename ``walk_forward_groups`` -> ``walk_forward_experiments`` (with
  ``grouping_key`` -> ``experiment_key``) and ``walk_forward_group_runs`` ->
  ``walk_forward_windows`` (with ``group_id`` -> ``experiment_id``);
- add a required ``backtest_runs.purpose`` discriminator so rolling-window runs
  are distinguishable from standalone runs (and, later, from optimizer
  evidence). It defaults to ``standalone``; the walk-forward path sets
  ``rolling_window`` explicitly;
- drop the copied ``average/median/best/worst_return_pct`` roll-ups from the
  experiment table — they are derived from the member runs at query time — and
  the redundant ``idx_walk_forward_group_runs_group_window`` index (the
  ``UNIQUE(experiment_id, window_index)`` constraint already indexes it).

These tables held no rows in the live database and carry no metadata worth
preserving, so this is a drop-and-recreate rather than an in-place data
migration: there is no backfill and no legacy labeling. The pre-migration
backup taken by ``manage_db_migrations`` is the retention path if a database
unexpectedly holds rows. Self-contained by convention: literal DDL only.
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# --- New (Program A) schema, parent tables first for FK creation order. ---
_NEW_TABLES = (
    """
    CREATE TABLE backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        strategy_id INTEGER,
        run_name TEXT,
        purpose TEXT NOT NULL DEFAULT 'standalone'
            CHECK (purpose IN ('standalone', 'rolling_window', 'walk_forward_oos', 'final_holdout')),
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        slippage_bps REAL NOT NULL DEFAULT 0,
        fee_per_trade REAL NOT NULL DEFAULT 0,
        tickers_file TEXT,
        notes TEXT,
        warnings TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id)
    )
    """,
    """
    CREATE TABLE backtest_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        execution_date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
        qty REAL NOT NULL,
        price REAL NOT NULL,
        fee REAL NOT NULL DEFAULT 0,
        slippage_bps REAL NOT NULL DEFAULT 0,
        note TEXT,
        FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE backtest_equity_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        snapshot_date TEXT NOT NULL,
        cash REAL NOT NULL,
        market_value REAL NOT NULL,
        equity REAL NOT NULL,
        realized_pnl REAL NOT NULL,
        unrealized_pnl REAL NOT NULL,
        FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE walk_forward_experiments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_key TEXT NOT NULL UNIQUE,
        account_id INTEGER NOT NULL,
        strategy_id INTEGER,
        run_name_prefix TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        test_months INTEGER NOT NULL,
        step_months INTEGER NOT NULL,
        window_count INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id)
    )
    """,
    """
    CREATE TABLE walk_forward_windows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id INTEGER NOT NULL,
        run_id INTEGER NOT NULL UNIQUE,
        window_index INTEGER NOT NULL,
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL,
        total_return_pct REAL NOT NULL,
        FOREIGN KEY (experiment_id) REFERENCES walk_forward_experiments(id) ON DELETE CASCADE,
        FOREIGN KEY (run_id) REFERENCES backtest_runs(id),
        UNIQUE(experiment_id, window_index)
    )
    """,
)

_NEW_INDEXES = (
    "CREATE INDEX idx_backtest_runs_account_id ON backtest_runs(account_id)",
    "CREATE INDEX idx_backtest_executions_run_id ON backtest_executions(run_id)",
    "CREATE INDEX idx_backtest_equity_run_id ON backtest_equity_snapshots(run_id)",
    (
        "CREATE INDEX idx_walk_forward_experiments_account_strategy_created "
        "ON walk_forward_experiments(account_id, strategy_id, created_at DESC)"
    ),
)

# --- Prior (0001) schema, restored empty by the downgrade. ---
_OLD_TABLES = (
    """
    CREATE TABLE backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        strategy_id INTEGER,
        run_name TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        slippage_bps REAL NOT NULL DEFAULT 0,
        fee_per_trade REAL NOT NULL DEFAULT 0,
        tickers_file TEXT,
        notes TEXT,
        warnings TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id)
    )
    """,
    """
    CREATE TABLE backtest_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        trade_time TEXT NOT NULL,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
        qty REAL NOT NULL,
        price REAL NOT NULL,
        fee REAL NOT NULL DEFAULT 0,
        slippage_bps REAL NOT NULL DEFAULT 0,
        note TEXT,
        FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE backtest_equity_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        snapshot_time TEXT NOT NULL,
        cash REAL NOT NULL,
        market_value REAL NOT NULL,
        equity REAL NOT NULL,
        realized_pnl REAL NOT NULL,
        unrealized_pnl REAL NOT NULL,
        FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE walk_forward_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grouping_key TEXT NOT NULL UNIQUE,
        account_id INTEGER NOT NULL,
        strategy_id INTEGER,
        run_name_prefix TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        test_months INTEGER NOT NULL,
        step_months INTEGER NOT NULL,
        window_count INTEGER NOT NULL,
        average_return_pct REAL NOT NULL,
        median_return_pct REAL NOT NULL,
        best_return_pct REAL NOT NULL,
        worst_return_pct REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id)
    )
    """,
    """
    CREATE TABLE walk_forward_group_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        run_id INTEGER NOT NULL UNIQUE,
        window_index INTEGER NOT NULL,
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL,
        total_return_pct REAL NOT NULL,
        FOREIGN KEY (group_id) REFERENCES walk_forward_groups(id) ON DELETE CASCADE,
        FOREIGN KEY (run_id) REFERENCES backtest_runs(id),
        UNIQUE(group_id, window_index)
    )
    """,
)

_OLD_INDEXES = (
    "CREATE INDEX idx_backtest_runs_account_id ON backtest_runs(account_id)",
    "CREATE INDEX idx_backtest_trades_run_id ON backtest_trades(run_id)",
    "CREATE INDEX idx_backtest_equity_run_id ON backtest_equity_snapshots(run_id)",
    (
        "CREATE INDEX idx_walk_forward_groups_account_strategy_created "
        "ON walk_forward_groups(account_id, strategy_id, created_at DESC)"
    ),
    "CREATE INDEX idx_walk_forward_group_runs_group_window ON walk_forward_group_runs(group_id, window_index ASC)",
)

# Drop children before parents so foreign keys never dangle mid-migration.
_DROP_NEW = (
    "walk_forward_windows",
    "walk_forward_experiments",
    "backtest_executions",
    "backtest_equity_snapshots",
    "backtest_runs",
)
_DROP_OLD = (
    "walk_forward_group_runs",
    "walk_forward_groups",
    "backtest_trades",
    "backtest_equity_snapshots",
    "backtest_runs",
)


def _drop_tables(names: tuple[str, ...]) -> None:
    for name in names:
        op.execute(f"DROP TABLE {name}")


def _run(statements: tuple[str, ...]) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _drop_tables(_DROP_OLD)
    _run(_NEW_TABLES)
    _run(_NEW_INDEXES)


def downgrade() -> None:
    _drop_tables(_DROP_NEW)
    _run(_OLD_TABLES)
    _run(_OLD_INDEXES)
