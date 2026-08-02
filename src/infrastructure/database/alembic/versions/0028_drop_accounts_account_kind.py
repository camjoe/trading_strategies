"""Drop accounts.account_kind.

Revision ID: 0028
Revises: 0027

``account_kind`` (``managed``/``local``) was meant to distinguish autonomous,
scheduler-run accounts from throwaway local accounts created just to try a
strategy. In practice no runtime path ever consulted it: the daily trading job
takes an explicit ``--accounts`` name list, backtesting accepts any account
name regardless of kind, and the walk-forward optimizer/promotion loop (which
now covers the "test a strategy without committing it to a live account"
use case ``local`` was meant for) has no account coupling at all. The only
production read was the autonomy dashboard's listing filter
(``account_kind == "managed"``), which just hid non-managed accounts from one
view rather than changing behavior. With that filter removed, the column
carries no live meaning and is dropped along with the rest of the
managed/local distinction in application code.

Self-contained by convention: no application imports, literal DDL only. No
CHECK constraint or index references this column (unlike ``risk_policy``'s
CHECK-constrained sibling), so a plain ``batch_alter_table`` drop applies —
no rebuild required.
"""

from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("account_kind")


def downgrade() -> None:
    # Restores schema shape only; discarded managed/local values do not come back.
    op.execute("ALTER TABLE accounts ADD COLUMN account_kind TEXT NOT NULL DEFAULT 'managed'")
