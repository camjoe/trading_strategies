from __future__ import annotations

import sqlite3

from trading.domain.promotion_models import PromotionAssessment
from trading.domain.promotion_policy import assess_promotion_readiness
from trading.services.evaluation_service import fetch_strategy_evaluation

YES_TEXT = "yes"
NO_TEXT = "no"
NONE_TEXT = "none"


def fetch_promotion_assessment(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    artifact = fetch_strategy_evaluation(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    return assess_promotion_readiness(artifact)


def _print_section(title: str, items: list[str]) -> None:
    print(f"{title}:")
    if not items:
        print(f"- {NONE_TEXT}")
        return
    for item in items:
        print(f"- {item}")


def show_promotion_status(
    conn: sqlite3.Connection,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    assessment = fetch_promotion_assessment(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    print("Promotion Status:")
    print(f"Account: {assessment.account_name}")
    print(f"Strategy: {assessment.strategy_name}")
    print(f"Stage: {assessment.stage}")
    print(f"Status: {assessment.status}")
    print(f"Ready for Live: {YES_TEXT if assessment.ready_for_live else NO_TEXT}")
    print(f"Live Trading Enabled: {YES_TEXT if assessment.live_trading_enabled else NO_TEXT}")
    print(f"Overall Confidence: {assessment.overall_confidence:.2f}")
    print(
        "Evaluation Generated At: "
        f"{assessment.evaluation_generated_at or NONE_TEXT}"
    )
    print(
        "Data Gaps: "
        + (", ".join(assessment.data_gaps) if assessment.data_gaps else NONE_TEXT)
    )
    print(f"Next Action: {assessment.next_action}")
    _print_section("Blockers", assessment.blockers)
    _print_section("Warnings", assessment.warnings)
    return assessment
