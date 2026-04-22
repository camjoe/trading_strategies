"""Promotion assessment queries for promotion consumers.

Owns computed promotion-readiness reads beneath the stable
``trading.services.promotion`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.domain.evaluation_models import StrategyEvaluationArtifact
from trading.domain.promotion_models import PromotionAssessment
from trading.domain.promotion_policy import assess_promotion_readiness
from trading.services.evaluation import fetch_strategy_evaluation
from trading.services.runtime_settings import fetch_promotion_policy_settings


def _fetch_current_promotion_snapshot(
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


def fetch_current_promotion_assessment(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    _, assessment = _fetch_current_promotion_snapshot(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    return assessment


def fetch_promotion_assessment(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    """Compatibility wrapper for the current computed promotion assessment."""
    return fetch_current_promotion_assessment(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )


__all__ = [
    "fetch_current_promotion_assessment",
    "fetch_promotion_assessment",
]
