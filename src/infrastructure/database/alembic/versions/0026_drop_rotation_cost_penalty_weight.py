"""Drop book_rotation_settings.cost_penalty_weight.

Revision ID: 0026
Revises: 0025

The column has never had an honest data source: a separate cost penalty on
top of backtest returns already net of modeled per-trade fees would
double-count, so it was excluded from the operator-tunable rotation policy
fields (``ROTATION_POLICY_FIELDS``) from the start and no application code
path ever writes a non-NULL value into it. Rather than keep reserving the
slot for a hypothetical future un-modeled-cost metric, this drops it — a
concrete future need can add a column (and a real ``cost_penalty`` score
component) when one actually exists.

Self-contained by convention: no application imports, literal DDL only.
SQLite requires ``batch_alter_table`` (copy-and-rebuild) for a column drop
(mirrors revision 0024's downgrade); no foreign keys are affected (unlike
revision 0014's regime-column drop, which needed a manual rebuild).

Guard: refuses to discard a populated value, matching revision 0014's
caution, even though no known write path produces one.
"""

from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    populated_row = (
        op.get_bind()
        .exec_driver_sql("SELECT book_id FROM book_rotation_settings WHERE cost_penalty_weight IS NOT NULL LIMIT 1")
        .fetchone()
    )
    if populated_row is not None:
        raise RuntimeError(
            "revision 0026 refuses to discard a populated book_rotation_settings.cost_penalty_weight; "
            f"book_id={populated_row[0]!r} has a value"
        )
    with op.batch_alter_table("book_rotation_settings") as batch:
        batch.drop_column("cost_penalty_weight")


def downgrade() -> None:
    # Restores schema shape empty; the upgrade guard ensures no value was discarded.
    op.execute("ALTER TABLE book_rotation_settings ADD COLUMN cost_penalty_weight REAL")
