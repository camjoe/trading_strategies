"""Seed module for promotion review data used in the shared seeded_conn fixture."""

from __future__ import annotations

import sqlite3

from tests.support.seed.accounts import ACCT_TREND, PROMOTION_STRATEGY, seed_account_id


def seed_promotion_review(conn: sqlite3.Connection) -> None:
    from trading.domain.evaluation_models import (
        EvaluationBacktestEvidence,
        EvaluationBasicScope,
        EvaluationConfidence,
        StrategyEvaluationArtifact,
    )
    from trading.domain.promotion_models import PromotionAssessment
    from trading.repositories.promotion import insert_promotion_review

    acct_id = seed_account_id(conn, ACCT_TREND)

    evaluation = StrategyEvaluationArtifact(
        basic=EvaluationBasicScope(
            account_id=acct_id,
            account_name=ACCT_TREND,
            requested_strategy=PROMOTION_STRATEGY,
            live_trading_enabled=False,
        ),
        backtest=EvaluationBacktestEvidence(
            available=True,
            trade_count=15,
            snapshot_count=30,
            total_return_pct=4.5,
            max_drawdown_pct=-8.0,
        ),
        confidence=EvaluationConfidence(overall_confidence=0.82),
    )
    assessment = PromotionAssessment(
        account_name=ACCT_TREND,
        strategy_name=PROMOTION_STRATEGY,
        stage="promotion_review",
        status="ready_for_review",
        ready_for_live=True,
        overall_confidence=0.82,
        next_action="Request operator review.",
    )
    insert_promotion_review(
        conn,
        assessment=assessment,
        evaluation=evaluation,
        requested_by="seed",
        operator_summary_note="",
        created_at="2026-01-15T00:00:00Z",
    )


__all__ = ["seed_promotion_review"]
