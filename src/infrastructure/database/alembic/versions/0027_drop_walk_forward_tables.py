"""Drop walk_forward_experiments and walk_forward_windows.

Revision ID: 0027
Revises: 0026

These tables backed the rolling-window ``backtest-walk-forward`` path, which ran
a fixed strategy across chronologically shifted windows and grouped the results.
That path was superseded by the walk-forward optimizer (revisions ``0021``-``0024``):
running the optimizer with a single-candidate search space reproduces it exactly
and adds a baseline comparison and an untouched holdout, so it produced no
evidence the optimizer cannot. Promotion, rotation, and the evaluation artifact
now read ``optimization_experiments``/``optimization_windows``, and the
rolling-window service, repository, report service, CLI commands, and web route
were removed alongside this revision.

The ``backtest_runs`` rows these windows referenced are deliberately left in
place: they are ordinary historical backtest runs and remain readable through the
run report. Only the grouping metadata is discarded.

Self-contained by convention: no application imports, literal DDL only. The
``rolling_window`` value stays in the ``backtest_runs.purpose`` CHECK constraint
so pre-existing rows remain valid; nothing writes it any more, and tightening the
constraint would mean rebuilding a populated table for no behavioral gain.
"""

from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_WALK_FORWARD_EXPERIMENTS_DDL = """
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
"""

_WALK_FORWARD_WINDOWS_DDL = """
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
"""

_EXPERIMENTS_INDEX_DDL = (
    "CREATE INDEX idx_walk_forward_experiments_account_strategy_created "
    "ON walk_forward_experiments(account_id, strategy_id, created_at DESC)"
)


def upgrade() -> None:
    # Windows first: they carry the FK to experiments.
    op.execute("DROP TABLE IF EXISTS walk_forward_windows")
    op.execute("DROP INDEX IF EXISTS idx_walk_forward_experiments_account_strategy_created")
    op.execute("DROP TABLE IF EXISTS walk_forward_experiments")


def downgrade() -> None:
    """Restore the table shapes from revision 0016. Data is not recoverable —
    restore a backup to recover the grouping rows themselves."""
    op.execute(_WALK_FORWARD_EXPERIMENTS_DDL)
    op.execute(_EXPERIMENTS_INDEX_DDL)
    op.execute(_WALK_FORWARD_WINDOWS_DDL)
