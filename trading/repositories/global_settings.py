from __future__ import annotations

import sqlite3


def fetch_global_settings_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM global_settings
        WHERE id = 1
        """
    ).fetchone()


def upsert_runtime_throttle_settings(
    conn: sqlite3.Connection,
    *,
    runtime_max_trades_per_day: int | None,
    runtime_max_trades_per_minute: int | None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO global_settings (
            id,
            runtime_max_trades_per_day,
            runtime_max_trades_per_minute,
            updated_at
        )
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            runtime_max_trades_per_day = excluded.runtime_max_trades_per_day,
            runtime_max_trades_per_minute = excluded.runtime_max_trades_per_minute,
            updated_at = excluded.updated_at
        """,
        (
            runtime_max_trades_per_day,
            runtime_max_trades_per_minute,
            updated_at,
        ),
    )
    conn.commit()


def upsert_evaluation_confidence_settings(
    conn: sqlite3.Connection,
    *,
    backtest_trade_count_for_full_confidence: int,
    backtest_snapshot_count_for_full_confidence: int,
    paper_live_snapshot_count_for_full_confidence: int,
    backtest_trade_confidence_weight: float,
    backtest_snapshot_confidence_weight: float,
    backtest_evidence_weight: float,
    paper_live_evidence_weight: float,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO global_settings (
            id,
            evaluation_backtest_trade_count_for_full_confidence,
            evaluation_backtest_snapshot_count_for_full_confidence,
            evaluation_paper_live_snapshot_count_for_full_confidence,
            evaluation_backtest_trade_confidence_weight,
            evaluation_backtest_snapshot_confidence_weight,
            evaluation_backtest_evidence_weight,
            evaluation_paper_live_evidence_weight,
            updated_at
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            evaluation_backtest_trade_count_for_full_confidence = excluded.evaluation_backtest_trade_count_for_full_confidence,
            evaluation_backtest_snapshot_count_for_full_confidence = excluded.evaluation_backtest_snapshot_count_for_full_confidence,
            evaluation_paper_live_snapshot_count_for_full_confidence = excluded.evaluation_paper_live_snapshot_count_for_full_confidence,
            evaluation_backtest_trade_confidence_weight = excluded.evaluation_backtest_trade_confidence_weight,
            evaluation_backtest_snapshot_confidence_weight = excluded.evaluation_backtest_snapshot_confidence_weight,
            evaluation_backtest_evidence_weight = excluded.evaluation_backtest_evidence_weight,
            evaluation_paper_live_evidence_weight = excluded.evaluation_paper_live_evidence_weight,
            updated_at = excluded.updated_at
        """,
        (
            backtest_trade_count_for_full_confidence,
            backtest_snapshot_count_for_full_confidence,
            paper_live_snapshot_count_for_full_confidence,
            backtest_trade_confidence_weight,
            backtest_snapshot_confidence_weight,
            backtest_evidence_weight,
            paper_live_evidence_weight,
            updated_at,
        ),
    )
    conn.commit()


def upsert_promotion_policy_settings(
    conn: sqlite3.Connection,
    *,
    min_research_backtest_trade_count: int,
    min_research_backtest_snapshot_count: int,
    min_research_backtest_return_pct: float,
    min_research_max_drawdown_pct: float,
    min_research_walk_forward_average_return_pct: float,
    min_live_paper_snapshot_count: int,
    min_live_overall_confidence: float,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO global_settings (
            id,
            promotion_min_research_backtest_trade_count,
            promotion_min_research_backtest_snapshot_count,
            promotion_min_research_backtest_return_pct,
            promotion_min_research_max_drawdown_pct,
            promotion_min_research_walk_forward_average_return_pct,
            promotion_min_live_paper_snapshot_count,
            promotion_min_live_overall_confidence,
            updated_at
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            promotion_min_research_backtest_trade_count = excluded.promotion_min_research_backtest_trade_count,
            promotion_min_research_backtest_snapshot_count = excluded.promotion_min_research_backtest_snapshot_count,
            promotion_min_research_backtest_return_pct = excluded.promotion_min_research_backtest_return_pct,
            promotion_min_research_max_drawdown_pct = excluded.promotion_min_research_max_drawdown_pct,
            promotion_min_research_walk_forward_average_return_pct = excluded.promotion_min_research_walk_forward_average_return_pct,
            promotion_min_live_paper_snapshot_count = excluded.promotion_min_live_paper_snapshot_count,
            promotion_min_live_overall_confidence = excluded.promotion_min_live_overall_confidence,
            updated_at = excluded.updated_at
        """,
        (
            min_research_backtest_trade_count,
            min_research_backtest_snapshot_count,
            min_research_backtest_return_pct,
            min_research_max_drawdown_pct,
            min_research_walk_forward_average_return_pct,
            min_live_paper_snapshot_count,
            min_live_overall_confidence,
            updated_at,
        ),
    )
    conn.commit()
