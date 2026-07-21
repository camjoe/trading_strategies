"""Rename the LEAPS/options exit-threshold columns on books.

Revision ID: 0011
Revises: 0010

The equity exit knobs (``stop_loss_pct``, ``take_profit_pct``) and the
LEAPS/options exit knobs (``profit_take_pct``, ``max_loss_pct``) were
distinguished only by word order, which is a persistent misread hazard. Rename
the LEAPS pair into the existing ``option_*`` column family so the instrument it
belongs to is legible from the name:

- ``profit_take_pct`` -> ``option_profit_take_pct``
- ``max_loss_pct``    -> ``option_max_loss_pct``

Pure column renames: ``ALTER TABLE ... RENAME COLUMN`` preserves the table's
CHECK constraints and indexes (none of which reference these columns), so no
copy-and-rebuild is required. Self-contained by convention: literal DDL only.
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE books RENAME COLUMN profit_take_pct TO option_profit_take_pct")
    op.execute("ALTER TABLE books RENAME COLUMN max_loss_pct TO option_max_loss_pct")


def downgrade() -> None:
    op.execute("ALTER TABLE books RENAME COLUMN option_profit_take_pct TO profit_take_pct")
    op.execute("ALTER TABLE books RENAME COLUMN option_max_loss_pct TO max_loss_pct")
