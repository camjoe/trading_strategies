"""Add counterfactual scoring columns to strategy_decisions.

Revision ID: 0004
Revises: 0003

A decision is scored against the alternative it rejected: both arms are backtested
over the window that actually happened, and the verdict comes from their difference.

- ``alternative_strategy_id`` is a write-once decision column; the write-once trigger
  is recreated to cover it.
- ``chosen_return_pct`` and ``alternative_return_pct`` are outcome columns.

Downgrade rebuilds the 0003 table shape, because SQLite cannot drop a column that
carries a foreign key; the dropped columns' values are recovered from backups.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TRIGGER_NAME = "trg_strategy_decisions_write_once"

_UPGRADE_TRIGGER = """
CREATE TRIGGER trg_strategy_decisions_write_once
BEFORE UPDATE ON strategy_decisions
WHEN NEW.account_id IS NOT OLD.account_id
    OR (NEW.book_id IS NOT OLD.book_id AND NEW.book_id IS NOT NULL)
    OR NEW.strategy_id IS NOT OLD.strategy_id
    OR NEW.alternative_strategy_id IS NOT OLD.alternative_strategy_id
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

# --- 0003 shape, restored by downgrade ---

_0003_CREATE_TABLE = """
CREATE TABLE strategy_decisions_new (
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

_0003_COLUMNS = (
    "id, account_id, book_id, strategy_id, decision_type, rationale, evidence_json, "
    "optimization_experiment_id, promotion_review_id, decided_by, created_at, outcome_window_days, "
    "outcome_status, outcome_window_start, outcome_window_end, realized_return_pct, "
    "realized_benchmark_return_pct, outcome_verdict, outcome_note, outcome_measured_at"
)

_0003_INDEXES = (
    "CREATE INDEX idx_strategy_decisions_account_created ON strategy_decisions(account_id, created_at)",
    "CREATE INDEX idx_strategy_decisions_strategy_created ON strategy_decisions(strategy_id, created_at)",
    "CREATE INDEX idx_strategy_decisions_outcome_status_created ON strategy_decisions(outcome_status, created_at)",
)

_0003_TRIGGER = """
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
    op.execute("ALTER TABLE strategy_decisions ADD COLUMN alternative_strategy_id INTEGER REFERENCES strategies(id)")
    op.execute("ALTER TABLE strategy_decisions ADD COLUMN chosen_return_pct REAL")
    op.execute("ALTER TABLE strategy_decisions ADD COLUMN alternative_return_pct REAL")
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME}")
    op.execute(_UPGRADE_TRIGGER)


def downgrade() -> None:
    op.execute(_0003_CREATE_TABLE)
    op.execute(f"INSERT INTO strategy_decisions_new ({_0003_COLUMNS}) SELECT {_0003_COLUMNS} FROM strategy_decisions")
    op.execute("DROP TABLE strategy_decisions")
    op.execute("ALTER TABLE strategy_decisions_new RENAME TO strategy_decisions")
    for index_sql in _0003_INDEXES:
        op.execute(index_sql)
    op.execute(_0003_TRIGGER)
