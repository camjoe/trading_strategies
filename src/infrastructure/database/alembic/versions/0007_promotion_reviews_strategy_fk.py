"""Add promotion_reviews.strategy_id FK; the name column becomes a snapshot.

Revision ID: 0007
Revises: 0006

promotion_reviews stored only a strategy name string, so renaming a strategy
key silently detached its review history (database-cleanup-roadmap item C1).
This applies the pattern the table already uses for accounts
(account_id + account_name_snapshot): a real strategies FK plus the existing
name column kept as the display snapshot. Backfill matches the normalized
name against strategies.strategy_key; rows whose names no longer resolve
keep a NULL id.

Self-contained by convention: no application imports, literal DDL only.
The downgrade is an explicit table rebuild (SQLite cannot drop a column that
carries a foreign-key clause).
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# The 0001 promotion_reviews columns (the downgrade copy list).
_BASE_COLUMNS = (
    "id",
    "account_id",
    "account_name_snapshot",
    "strategy_name",
    "review_state",
    "assessment_stage",
    "assessment_status",
    "ready_for_live",
    "overall_confidence",
    "live_trading_enabled_snapshot",
    "promotion_assessment_version",
    "evaluation_artifact_version",
    "frozen_assessment_payload",
    "frozen_evaluation_payload",
    "requested_by",
    "reviewed_by",
    "operator_summary_note",
    "created_at",
    "updated_at",
    "closed_at",
)

_BASE_DDL = """
    CREATE TABLE promotion_reviews_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        account_name_snapshot TEXT NOT NULL,
        strategy_name TEXT NOT NULL,
        review_state TEXT NOT NULL DEFAULT 'requested',
        assessment_stage TEXT NOT NULL,
        assessment_status TEXT NOT NULL,
        ready_for_live INTEGER NOT NULL DEFAULT 0,
        overall_confidence REAL NOT NULL DEFAULT 0,
        live_trading_enabled_snapshot INTEGER NOT NULL DEFAULT 0,
        promotion_assessment_version TEXT NOT NULL,
        evaluation_artifact_version TEXT NOT NULL,
        frozen_assessment_payload TEXT NOT NULL,
        frozen_evaluation_payload TEXT NOT NULL,
        requested_by TEXT,
        reviewed_by TEXT,
        operator_summary_note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        closed_at TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    )
"""

_INDEXES = (
    (
        "CREATE INDEX idx_promotion_reviews_account_strategy_created "
        "ON promotion_reviews(account_id, strategy_name, created_at DESC)"
    ),
    "CREATE INDEX idx_promotion_reviews_state_updated ON promotion_reviews(review_state, updated_at DESC)",
    (
        "CREATE UNIQUE INDEX idx_promotion_reviews_open_requested "
        "ON promotion_reviews(account_id, strategy_name) WHERE review_state = 'requested'"
    ),
)


def upgrade() -> None:
    op.execute("ALTER TABLE promotion_reviews ADD COLUMN strategy_id INTEGER REFERENCES strategies(id)")
    op.execute(
        """
        UPDATE promotion_reviews
        SET strategy_id = (
            SELECT s.id FROM strategies s
            WHERE s.strategy_key = LOWER(TRIM(promotion_reviews.strategy_name))
        )
        """
    )
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check(promotion_reviews)").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0007 backfill left FK violations: {orphans!r}")


def downgrade() -> None:
    column_list = ", ".join(_BASE_COLUMNS)
    op.execute(_BASE_DDL)
    op.execute(f"INSERT INTO promotion_reviews_new ({column_list}) SELECT {column_list} FROM promotion_reviews")
    op.execute("DROP TABLE promotion_reviews")
    op.execute("ALTER TABLE promotion_reviews_new RENAME TO promotion_reviews")
    for index_sql in _INDEXES:
        op.execute(index_sql)
