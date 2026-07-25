"""Add optimization_windows + optimization_trials for optimizer audit depth.

Revision ID: 0022
Revises: 0021

Deepens the walk-forward optimizer's persistence from the single Tier-1
``optimization_experiments`` row (0021) to per-window and per-candidate detail —
the *multiple-testing* audit control: persist every attempted candidate, not just
the forward-carried winner.

``optimization_windows`` — one row per walk-forward window: the four train/test
boundaries (persisted nowhere before this) and ``oos_run_id``, which links the
window's persisted winner OOS ``backtest_runs`` row. Before this revision those
per-window OOS runs existed (``purpose='walk_forward_oos'``) but only the holdout
run was linked back to the experiment, so they were effectively orphaned; this
column closes that gap. OOS metrics are read from the linked ``backtest_runs``
row, never copied here (the same link-don't-copy discipline the walk-forward
rolling-window tables already adopted).

``optimization_trials`` — one row per grid candidate per window: canonical params
+ hash, the objective value and its components, eligibility + structured
rejection reason, and the ``selected`` winner flag. Training candidates are
evaluated metrics-only (never ``backtest_runs`` rows), so this table is the sole
record of the attempted search. Two partial/unique indexes encode the
invariants: one candidate hash per window, and at most one selected trial per
window.

Cascade flows experiment -> window -> trial (both child tables cascade-delete),
so an ``optimization_experiments`` delete cleans up its full audit subtree. The
winner is recorded only by ``optimization_trials.selected`` (no redundant
back-link on the window); trials carry only ``window_id`` (the experiment is
reached by join).

Self-contained by convention: no application imports, literal DDL only. Two new
child tables (pure CREATE); the downgrade drops them (trials first, then windows,
respecting the FK direction).
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE optimization_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            window_index INTEGER NOT NULL,
            train_start TEXT NOT NULL,
            train_end TEXT NOT NULL,
            test_start TEXT NOT NULL,
            test_end TEXT NOT NULL,
            oos_run_id INTEGER NOT NULL,
            FOREIGN KEY (experiment_id) REFERENCES optimization_experiments(id) ON DELETE CASCADE,
            FOREIGN KEY (oos_run_id) REFERENCES backtest_runs(id)
        )
        """
    )
    # Unique per (experiment, window) and the covering index for the experiment
    # cascade — experiment_id is the leading column, so no separate FK index is needed.
    op.execute(
        "CREATE UNIQUE INDEX idx_optimization_windows_experiment_window "
        "ON optimization_windows(experiment_id, window_index)"
    )

    op.execute(
        """
        CREATE TABLE optimization_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_id INTEGER NOT NULL,
            candidate_index INTEGER NOT NULL,
            params_json TEXT NOT NULL,
            params_hash TEXT NOT NULL,
            objective_value REAL,
            annualized_return_pct REAL,
            max_drawdown_pct REAL NOT NULL,
            trade_count INTEGER NOT NULL,
            eligible INTEGER NOT NULL,
            rejection_reason TEXT,
            selected INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (window_id) REFERENCES optimization_windows(id) ON DELETE CASCADE
        )
        """
    )
    # One candidate (by canonical params hash) per window. Leading column window_id
    # also covers the window cascade FK.
    op.execute(
        "CREATE UNIQUE INDEX idx_optimization_trials_window_hash "
        "ON optimization_trials(window_id, params_hash)"
    )
    # At most one selected winner per window (partial unique index).
    op.execute(
        "CREATE UNIQUE INDEX idx_optimization_trials_selected_per_window "
        "ON optimization_trials(window_id) WHERE selected = 1"
    )


def downgrade() -> None:
    op.execute("DROP TABLE optimization_trials")
    op.execute("DROP TABLE optimization_windows")
