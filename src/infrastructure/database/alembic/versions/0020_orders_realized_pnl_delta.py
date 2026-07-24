"""Add orders.realized_pnl_delta.

Revision ID: 0020
Revises: 0019

Gives a closing order's realized P&L a persisted home. The value is already
computed at fill time by ``apply_book_fill_transition`` (sell proceeds minus the
position's average cost, net of commission) but was discarded after updating
balances. Persisting it lets the daily-metrics writer derive ``hit_rate`` and
``expectancy`` — the two columns it currently leaves NULL for lack of per-trade
realized P&L.

Nullable by design: it is populated only for orders that *closed* a position
(sells). Opening orders (buys) realize nothing and stay NULL, so
``realized_pnl_delta IS NOT NULL`` cleanly identifies a closing trade — a plain
zero would be ambiguous with a break-even close. Existing rows stay NULL (no
backfill); the writer populates going forward.

Self-contained by convention: no application imports, literal DDL only. A plain
additive nullable column (ADD COLUMN); the downgrade drops it via a batch
rebuild (SQLite cannot drop a column in place against the unnamed constraints).
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0020 rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN realized_pnl_delta REAL")


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("realized_pnl_delta")
    _check_foreign_keys()
