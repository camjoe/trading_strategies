"""Add the strategy_decisions ledger.

Revision ID: 0003
Revises: 0002

One row per advisor decision (including ``hold``) with the frozen evidence it
rested on, plus outcome columns filled after the decision's window has elapsed.

``optimization_experiment_id`` is a plain id with no foreign key: the experiment
table belongs to the backtesting context, and the frozen ``evidence_json`` is the
durable record if that experiment is later deleted.

Decision columns are write-once, enforced by a trigger. ``book_id`` and
``promotion_review_id`` may change only to NULL, because their ``ON DELETE SET
NULL`` actions run as updates.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_CREATE_TABLE = """
CREATE TABLE strategy_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    book_id INTEGER,
    strategy_id INTEGER REFERENCES strategies(id),
    decision_type TEXT NOT NULL CHECK (
        decision_type IN (
            'hold',
            'adjust_params',
            'propose_variant',
            'request_promotion',
            'disable_strategy',
            'run_experiment'
        )
    ),
    rationale TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    optimization_experiment_id INTEGER,
    promotion_review_id INTEGER,
    decided_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    outcome_window_days INTEGER NOT NULL DEFAULT 21 CHECK (outcome_window_days > 0),
    outcome_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        outcome_status IN ('pending', 'measured', 'inconclusive')
    ),
    outcome_window_start TEXT,
    outcome_window_end TEXT,
    realized_return_pct REAL,
    realized_benchmark_return_pct REAL,
    outcome_verdict TEXT CHECK (
        outcome_verdict IS NULL OR outcome_verdict IN ('helped', 'neutral', 'hurt')
    ),
    outcome_note TEXT,
    outcome_measured_at TEXT,
    CHECK (
        outcome_status <> 'measured'
        OR (outcome_verdict IS NOT NULL AND outcome_measured_at IS NOT NULL)
    ),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE SET NULL,
    FOREIGN KEY (book_id, account_id) REFERENCES books(id, account_id),
    FOREIGN KEY (promotion_review_id) REFERENCES promotion_reviews(id) ON DELETE SET NULL
)
"""

_CREATE_INDEXES = (
    "CREATE INDEX idx_strategy_decisions_account_created ON strategy_decisions(account_id, created_at)",
    "CREATE INDEX idx_strategy_decisions_strategy_created ON strategy_decisions(strategy_id, created_at)",
    "CREATE INDEX idx_strategy_decisions_outcome_status_created ON strategy_decisions(outcome_status, created_at)",
)

_CREATE_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER trg_strategy_decisions_write_once
BEFORE UPDATE ON strategy_decisions
WHEN NEW.account_id IS NOT OLD.account_id
    OR (NEW.book_id IS NOT OLD.book_id AND NEW.book_id IS NOT NULL)
    OR NEW.strategy_id IS NOT OLD.strategy_id
    OR NEW.decision_type IS NOT OLD.decision_type
    OR NEW.rationale IS NOT OLD.rationale
    OR NEW.evidence_json IS NOT OLD.evidence_json
    OR NEW.optimization_experiment_id IS NOT OLD.optimization_experiment_id
    OR (NEW.promotion_review_id IS NOT OLD.promotion_review_id AND NEW.promotion_review_id IS NOT NULL)
    OR NEW.decided_by IS NOT OLD.decided_by
    OR NEW.created_at IS NOT OLD.created_at
    OR NEW.outcome_window_days IS NOT OLD.outcome_window_days
BEGIN
    SELECT RAISE(ABORT, 'strategy_decisions decision fields are write-once');
END
"""


def upgrade() -> None:
    op.execute(_CREATE_TABLE)
    for index_sql in _CREATE_INDEXES:
        op.execute(index_sql)
    op.execute(_CREATE_IMMUTABILITY_TRIGGER)


def downgrade() -> None:
    # Dropping the table also drops its indexes and trigger.
    op.execute("DROP TABLE strategy_decisions")
