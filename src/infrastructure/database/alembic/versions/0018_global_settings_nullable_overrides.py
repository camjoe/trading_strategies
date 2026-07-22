"""Make global policy settings nullable code-default overrides.

Revision ID: 0018
Revises: 0017

``global_settings`` stores operator overrides, while the evaluation and
promotion domain settings classes own the effective code defaults. Previously,
creating the singleton row for an unrelated throttle caused SQLite defaults to
materialize every evaluation and promotion value. Making those policy columns
nullable preserves the distinction between an explicit override and an
untouched code default.

The upgrade preserves every existing value. The downgrade restores the prior
NOT NULL shape by replacing NULL overrides with the literal defaults frozen in
revision 0001; a pre-downgrade backup is required to recover which values were
previously unset.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_COLUMNS = (
    "id",
    "runtime_max_trades_per_day",
    "runtime_max_trades_per_minute",
    "evaluation_backtest_trade_count_for_full_confidence",
    "evaluation_backtest_snapshot_count_for_full_confidence",
    "evaluation_paper_live_snapshot_count_for_full_confidence",
    "evaluation_backtest_trade_confidence_weight",
    "evaluation_backtest_snapshot_confidence_weight",
    "evaluation_backtest_evidence_weight",
    "evaluation_paper_live_evidence_weight",
    "promotion_min_research_backtest_trade_count",
    "promotion_min_research_backtest_snapshot_count",
    "promotion_min_research_backtest_return_pct",
    "promotion_min_research_max_drawdown_pct",
    "promotion_min_research_walk_forward_average_return_pct",
    "promotion_min_live_paper_snapshot_count",
    "promotion_min_live_overall_confidence",
    "updated_at",
)

_NULLABLE_TABLE = """
    CREATE TABLE global_settings_new (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        runtime_max_trades_per_day INTEGER CHECK (
            runtime_max_trades_per_day IS NULL OR runtime_max_trades_per_day >= 1
        ),
        runtime_max_trades_per_minute INTEGER CHECK (
            runtime_max_trades_per_minute IS NULL OR runtime_max_trades_per_minute >= 1
        ),
        evaluation_backtest_trade_count_for_full_confidence INTEGER CHECK (
            evaluation_backtest_trade_count_for_full_confidence IS NULL
            OR evaluation_backtest_trade_count_for_full_confidence >= 1
        ),
        evaluation_backtest_snapshot_count_for_full_confidence INTEGER CHECK (
            evaluation_backtest_snapshot_count_for_full_confidence IS NULL
            OR evaluation_backtest_snapshot_count_for_full_confidence >= 1
        ),
        evaluation_paper_live_snapshot_count_for_full_confidence INTEGER CHECK (
            evaluation_paper_live_snapshot_count_for_full_confidence IS NULL
            OR evaluation_paper_live_snapshot_count_for_full_confidence >= 1
        ),
        evaluation_backtest_trade_confidence_weight REAL CHECK (
            evaluation_backtest_trade_confidence_weight IS NULL
            OR evaluation_backtest_trade_confidence_weight BETWEEN 0 AND 1
        ),
        evaluation_backtest_snapshot_confidence_weight REAL CHECK (
            evaluation_backtest_snapshot_confidence_weight IS NULL
            OR evaluation_backtest_snapshot_confidence_weight BETWEEN 0 AND 1
        ),
        evaluation_backtest_evidence_weight REAL CHECK (
            evaluation_backtest_evidence_weight IS NULL
            OR evaluation_backtest_evidence_weight BETWEEN 0 AND 1
        ),
        evaluation_paper_live_evidence_weight REAL CHECK (
            evaluation_paper_live_evidence_weight IS NULL
            OR evaluation_paper_live_evidence_weight BETWEEN 0 AND 1
        ),
        promotion_min_research_backtest_trade_count INTEGER CHECK (
            promotion_min_research_backtest_trade_count IS NULL
            OR promotion_min_research_backtest_trade_count >= 1
        ),
        promotion_min_research_backtest_snapshot_count INTEGER CHECK (
            promotion_min_research_backtest_snapshot_count IS NULL
            OR promotion_min_research_backtest_snapshot_count >= 1
        ),
        promotion_min_research_backtest_return_pct REAL,
        promotion_min_research_max_drawdown_pct REAL,
        promotion_min_research_walk_forward_average_return_pct REAL,
        promotion_min_live_paper_snapshot_count INTEGER CHECK (
            promotion_min_live_paper_snapshot_count IS NULL
            OR promotion_min_live_paper_snapshot_count >= 1
        ),
        promotion_min_live_overall_confidence REAL CHECK (
            promotion_min_live_overall_confidence IS NULL
            OR promotion_min_live_overall_confidence BETWEEN 0 AND 1
        ),
        updated_at TEXT
    )
"""

_PRIOR_TABLE = """
    CREATE TABLE global_settings_new (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        runtime_max_trades_per_day INTEGER CHECK (
            runtime_max_trades_per_day IS NULL OR runtime_max_trades_per_day >= 1
        ),
        runtime_max_trades_per_minute INTEGER CHECK (
            runtime_max_trades_per_minute IS NULL OR runtime_max_trades_per_minute >= 1
        ),
        evaluation_backtest_trade_count_for_full_confidence INTEGER NOT NULL DEFAULT 50 CHECK (
            evaluation_backtest_trade_count_for_full_confidence >= 1
        ),
        evaluation_backtest_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 60 CHECK (
            evaluation_backtest_snapshot_count_for_full_confidence >= 1
        ),
        evaluation_paper_live_snapshot_count_for_full_confidence INTEGER NOT NULL DEFAULT 30 CHECK (
            evaluation_paper_live_snapshot_count_for_full_confidence >= 1
        ),
        evaluation_backtest_trade_confidence_weight REAL NOT NULL DEFAULT 0.7 CHECK (
            evaluation_backtest_trade_confidence_weight BETWEEN 0 AND 1
        ),
        evaluation_backtest_snapshot_confidence_weight REAL NOT NULL DEFAULT 0.3 CHECK (
            evaluation_backtest_snapshot_confidence_weight BETWEEN 0 AND 1
        ),
        evaluation_backtest_evidence_weight REAL NOT NULL DEFAULT 0.6 CHECK (
            evaluation_backtest_evidence_weight BETWEEN 0 AND 1
        ),
        evaluation_paper_live_evidence_weight REAL NOT NULL DEFAULT 0.4 CHECK (
            evaluation_paper_live_evidence_weight BETWEEN 0 AND 1
        ),
        promotion_min_research_backtest_trade_count INTEGER NOT NULL DEFAULT 10 CHECK (
            promotion_min_research_backtest_trade_count >= 1
        ),
        promotion_min_research_backtest_snapshot_count INTEGER NOT NULL DEFAULT 20 CHECK (
            promotion_min_research_backtest_snapshot_count >= 1
        ),
        promotion_min_research_backtest_return_pct REAL NOT NULL DEFAULT 0.0,
        promotion_min_research_max_drawdown_pct REAL NOT NULL DEFAULT -25.0,
        promotion_min_research_walk_forward_average_return_pct REAL NOT NULL DEFAULT 0.0,
        promotion_min_live_paper_snapshot_count INTEGER NOT NULL DEFAULT 10 CHECK (
            promotion_min_live_paper_snapshot_count >= 1
        ),
        promotion_min_live_overall_confidence REAL NOT NULL DEFAULT 0.6 CHECK (
            promotion_min_live_overall_confidence BETWEEN 0 AND 1
        ),
        updated_at TEXT
    )
"""

_DOWNGRADE_SELECT = (
    "id",
    "runtime_max_trades_per_day",
    "runtime_max_trades_per_minute",
    "COALESCE(evaluation_backtest_trade_count_for_full_confidence, 50)",
    "COALESCE(evaluation_backtest_snapshot_count_for_full_confidence, 60)",
    "COALESCE(evaluation_paper_live_snapshot_count_for_full_confidence, 30)",
    "COALESCE(evaluation_backtest_trade_confidence_weight, 0.7)",
    "COALESCE(evaluation_backtest_snapshot_confidence_weight, 0.3)",
    "COALESCE(evaluation_backtest_evidence_weight, 0.6)",
    "COALESCE(evaluation_paper_live_evidence_weight, 0.4)",
    "COALESCE(promotion_min_research_backtest_trade_count, 10)",
    "COALESCE(promotion_min_research_backtest_snapshot_count, 20)",
    "COALESCE(promotion_min_research_backtest_return_pct, 0.0)",
    "COALESCE(promotion_min_research_max_drawdown_pct, -25.0)",
    "COALESCE(promotion_min_research_walk_forward_average_return_pct, 0.0)",
    "COALESCE(promotion_min_live_paper_snapshot_count, 10)",
    "COALESCE(promotion_min_live_overall_confidence, 0.6)",
    "updated_at",
)


def _swap() -> None:
    op.execute("DROP TABLE global_settings")
    op.execute("ALTER TABLE global_settings_new RENAME TO global_settings")
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check(global_settings)").fetchall()
    if orphans:
        raise RuntimeError(f"global_settings rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    columns = ", ".join(_COLUMNS)
    op.execute(_NULLABLE_TABLE)
    op.execute(f"INSERT INTO global_settings_new ({columns}) SELECT {columns} FROM global_settings")
    _swap()


def downgrade() -> None:
    columns = ", ".join(_COLUMNS)
    select_expressions = ", ".join(_DOWNGRADE_SELECT)
    op.execute(_PRIOR_TABLE)
    op.execute(f"INSERT INTO global_settings_new ({columns}) SELECT {select_expressions} FROM global_settings")
    _swap()
