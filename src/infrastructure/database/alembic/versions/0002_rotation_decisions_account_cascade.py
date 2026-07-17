"""Rebuild rotation_decisions with book_id ON DELETE CASCADE.

Revision ID: 0002
Revises: 0001

The 0001 shape used ON DELETE RESTRICT on rotation_decisions.book_id. SQLite
enforces RESTRICT immediately, even mid-cascade, so `DELETE FROM accounts`
failed for any account whose books had rotation history (accounts -> books
cascade hits the RESTRICT). Rotation decisions are book-owned operational
history like daily_metrics and equity_snapshots; account deletion removes
them, and the pre-deletion backup remains the retention path.

Self-contained by convention: no application imports, literal DDL only.
SQLite cannot alter FK actions in place, so both directions are explicit
table rebuilds (create new -> copy -> drop -> rename -> recreate indexes).
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Explicit copy list — rebuilds must never use SELECT *.
_COLUMNS = (
    "id",
    "book_id",
    "decision_time",
    "incumbent_strategy_id",
    "challenger_strategy_id",
    "selected_strategy_id",
    "rotation_action",
    "cooldown_active",
    "decision_score",
    "decision_confidence",
    "score_components_json",
    "gate_results_json",
    "decision_reason",
    "config_version",
    "window_start",
    "window_end",
    "realized_pnl_delta",
    "created_at",
)

_INDEXES = (
    "CREATE INDEX idx_rotation_decisions_book_time ON rotation_decisions(book_id, decision_time DESC)",
    (
        "CREATE INDEX idx_rotation_decisions_action_time_book "
        "ON rotation_decisions(rotation_action, decision_time DESC)"
    ),
)


def _create_table_sql(book_fk_action: str) -> str:
    return f"""
        CREATE TABLE rotation_decisions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            decision_time TEXT NOT NULL,
            incumbent_strategy_id INTEGER,
            challenger_strategy_id INTEGER,
            selected_strategy_id INTEGER,
            rotation_action TEXT NOT NULL CHECK (rotation_action IN ('hold', 'rotate')),
            cooldown_active INTEGER NOT NULL DEFAULT 0,
            decision_score REAL,
            decision_confidence REAL,
            score_components_json TEXT NOT NULL,
            gate_results_json TEXT NOT NULL,
            decision_reason TEXT,
            config_version TEXT,
            window_start TEXT,
            window_end TEXT,
            realized_pnl_delta REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE {book_fk_action},
            FOREIGN KEY (incumbent_strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (challenger_strategy_id) REFERENCES strategies(id),
            FOREIGN KEY (selected_strategy_id) REFERENCES strategies(id)
        )
    """


def _rebuild(book_fk_action: str) -> None:
    column_list = ", ".join(_COLUMNS)
    op.execute(_create_table_sql(book_fk_action))
    op.execute(f"INSERT INTO rotation_decisions_new ({column_list}) SELECT {column_list} FROM rotation_decisions")
    op.execute("DROP TABLE rotation_decisions")
    op.execute("ALTER TABLE rotation_decisions_new RENAME TO rotation_decisions")
    for index_sql in _INDEXES:
        op.execute(index_sql)
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check(rotation_decisions)").fetchall()
    if orphans:
        raise RuntimeError(f"rotation_decisions rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    _rebuild("CASCADE")


def downgrade() -> None:
    # Restores the 0001 RESTRICT shape; account deletion for accounts with
    # rotation history fails again under this shape.
    _rebuild("RESTRICT")
