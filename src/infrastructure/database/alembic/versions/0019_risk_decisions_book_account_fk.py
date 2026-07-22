"""Enforce that risk-decision books belong to their recorded accounts.

Revision ID: 0019
Revises: 0018

Book-level risk decisions store both the execution book and its account for
account-level reporting. Add the composite relationship that prevents those
identifiers from drifting while preserving nullable book ids for account-level
decisions. The existing single-column book FK retains ON DELETE SET NULL.
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_COLUMNS = (
    "id",
    "account_id",
    "book_id",
    "decision_time",
    "symbol",
    "side",
    "action",
    "reason_code",
    "requested_qty",
    "approved_qty",
    "requested_notional",
    "approved_notional",
    "risk_payload_json",
    "created_at",
)

_TABLE_TEMPLATE = """
    CREATE TABLE risk_decisions_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        book_id INTEGER,
        decision_time TEXT NOT NULL,
        symbol TEXT,
        side TEXT CHECK (side IS NULL OR side IN ('buy', 'sell')),
        action TEXT NOT NULL CHECK (action IN ('allow', 'rescale', 'block')),
        reason_code TEXT NOT NULL,
        requested_qty REAL,
        approved_qty REAL,
        requested_notional REAL,
        approved_notional REAL,
        risk_payload_json TEXT NOT NULL DEFAULT '{{}}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE SET NULL
        {composite_fk}
    )
"""

_COMPOSITE_FK = ",\n        FOREIGN KEY (book_id, account_id) REFERENCES books(id, account_id)"

_INDEXES = (
    "CREATE INDEX idx_risk_decisions_account_time ON risk_decisions(account_id, decision_time DESC)",
    "CREATE INDEX idx_risk_decisions_book_time ON risk_decisions(book_id, decision_time DESC)",
)


def _rebuild(*, composite_fk: str) -> None:
    columns = ", ".join(_COLUMNS)
    op.execute(_TABLE_TEMPLATE.format(composite_fk=composite_fk))
    op.execute(f"INSERT INTO risk_decisions_new ({columns}) SELECT {columns} FROM risk_decisions")
    op.execute("DROP TABLE risk_decisions")
    op.execute("ALTER TABLE risk_decisions_new RENAME TO risk_decisions")
    for index_sql in _INDEXES:
        op.execute(index_sql)
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"risk_decisions rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX idx_books_id_account ON books(id, account_id)")
    _rebuild(composite_fk=_COMPOSITE_FK)


def downgrade() -> None:
    _rebuild(composite_fk="")
    op.execute("DROP INDEX idx_books_id_account")
