"""Add failure state columns to optimization_experiments.

Revision ID: 0024
Revises: 0023

Item 5 of the walk-forward optimizer plan ("fail-fast experiment state"):
today a run that fails partway through (a training window with no eligible
candidate, a market-data/DB error, ...) leaves no persisted trace — the
exception propagates to a bare CLI error and nothing is written. These columns
let a failed run persist one audit row: which lifecycle stage it failed in,
why, and (via the existing ``window_count`` column) how many windows completed
first. ``status`` defaults every existing row to ``'completed'`` (they all are);
``failure_stage``/``failure_message`` stay ``NULL`` for those rows.

Deliberately minimal: no columns added to ``optimization_windows`` /
``optimization_trials`` / ``optimization_run_manifests`` — a failed experiment
does not get a partial per-window/candidate audit tree, only this one
experiment-level record.

Self-contained by convention: no application imports, literal DDL only.
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE optimization_experiments ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
    op.execute("ALTER TABLE optimization_experiments ADD COLUMN failure_stage TEXT")
    op.execute("ALTER TABLE optimization_experiments ADD COLUMN failure_message TEXT")


def downgrade() -> None:
    # Restores schema shape; discarded values come back from backups, not downgrades.
    with op.batch_alter_table("optimization_experiments") as batch:
        batch.drop_column("failure_message")
        batch.drop_column("failure_stage")
        batch.drop_column("status")
