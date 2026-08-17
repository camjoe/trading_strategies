"""Promotion assessment queries for promotion consumers.

Owns computed promotion-readiness reads beneath the stable
``trading.services.promotion`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.domain.promotion.policy import assess_promotion_readiness
from trading.models.evaluation import StrategyEvaluationArtifact
from trading.models.promotion import PromotionAssessment
from trading.services.evaluation.queries import fetch_strategy_evaluation
from trading.services.operational_settings.queries import fetch_promotion_policy_settings


def fetch_promotion_snapshot(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> tuple[StrategyEvaluationArtifact, PromotionAssessment]:
    artifact = fetch_strategy_evaluation(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    return artifact, assess_promotion_readiness(
        artifact,
        settings=fetch_promotion_policy_settings(conn),
    )


def fetch_promotion_assessment(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    _, assessment = fetch_promotion_snapshot(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    return assessment


__all__ = [
    "fetch_promotion_assessment",
    "fetch_promotion_snapshot",
]
