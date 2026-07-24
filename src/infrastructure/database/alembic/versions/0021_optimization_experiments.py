"""Add optimization_experiments for walk-forward optimizer promotion.

Revision ID: 0021
Revises: 0020

Persists one row per ``backtest-optimize`` run so a validated winner can be
reviewed and promoted into a tradeable ``strategies`` variant with an auditable
basis. This is the Tier-1 persistence for the operational optimize -> promote
loop: run config, the forward-carried winner parameters, a small out-of-sample
aggregate, the untouched-holdout summary, and the promoted-variant link.

Per-window and per-candidate detail (optimization_windows / optimization_trials)
are deliberately out of scope here — the operational loop does not need them yet.

Baseline (default-parameter) OOS/holdout numbers are summarized on this row
because the optimizer runs the baseline metrics-only (they are not persisted as
``backtest_runs``). ``holdout_run_id`` links the persisted winner-holdout run;
``promoted_strategy_id`` is set when the winner is promoted.

Self-contained by convention: no application imports, literal DDL only. A new
parent table (pure CREATE); the downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE optimization_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            strategy_id INTEGER,
            primitive TEXT NOT NULL,
            objective_name TEXT NOT NULL,
            search_space_json TEXT NOT NULL,
            candidate_budget INTEGER NOT NULL,
            train_months INTEGER NOT NULL,
            test_months INTEGER NOT NULL,
            step_months INTEGER NOT NULL,
            holdout_months INTEGER NOT NULL,
            warmup_months INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            window_count INTEGER NOT NULL,
            winner_params_json TEXT NOT NULL,
            oos_mean_winner_return_pct REAL,
            oos_mean_baseline_return_pct REAL,
            oos_windows_beat_baseline INTEGER,
            holdout_run_id INTEGER,
            holdout_winner_return_pct REAL,
            holdout_baseline_return_pct REAL,
            promoted_strategy_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (holdout_run_id) REFERENCES backtest_runs(id),
            FOREIGN KEY (promoted_strategy_id) REFERENCES strategies(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_optimization_experiments_account_strategy_created "
        "ON optimization_experiments(account_id, strategy_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE optimization_experiments")
