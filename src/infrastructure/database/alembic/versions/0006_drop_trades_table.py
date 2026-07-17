"""Drop the legacy account-level trades table.

Revision ID: 0006
Revises: 0005

The trades table duplicated the book execution history: every runtime fill
double-wrote an orders/order_fills row (book-keyed, authoritative) and a
trades row via the on_fill bridge (database-cleanup-roadmap item B1, decided
2026-07-16). Account state now replays order fills plus ledger
deposit/withdrawal entries; manual entries create filled orders or ledger
cash events on the default book. The pre-migration backup is the retention
path for historical trades rows (including their free-text notes, which the
clean tables do not carry).

Self-contained by convention: no application imports, literal DDL only.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# The 0001 trades shape, restored (empty) by the downgrade.
_TRADES_DDL = """
    CREATE TABLE trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
        qty REAL NOT NULL,
        price REAL NOT NULL,
        fee REAL NOT NULL DEFAULT 0,
        trade_time TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    )
"""


def upgrade() -> None:
    op.execute("DROP TABLE trades")


def downgrade() -> None:
    # Restores the table shape only; the pre-migration backup recovers data.
    op.execute(_TRADES_DDL)
    op.execute("CREATE INDEX idx_trades_trade_time ON trades(trade_time)")
