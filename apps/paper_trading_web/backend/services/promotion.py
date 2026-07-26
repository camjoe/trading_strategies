from __future__ import annotations

import sqlite3

from trading.services.promotion import (
    fetch_promotion_review_history,
    fetch_promotion_snapshot,
)

from .evaluation import build_evaluation_detail_payload


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def build_promotion_overview(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
    limit: int = 5,
) -> dict[str, object]:
    normalized_strategy_name = _normalize_optional_text(strategy_name)
    evaluation, assessment = fetch_promotion_snapshot(
        conn,
        account_name=account_name,
        strategy_name=normalized_strategy_name,
    )
    history = fetch_promotion_review_history(
        conn,
        account_name=account_name,
        strategy_name=normalized_strategy_name,
        limit=limit,
    )
    return {
        "assessment": assessment.to_payload(),
        "evaluation": build_evaluation_detail_payload(evaluation),
        "history": [
            {
                "review": entry.review.to_payload(),
                "events": [event.to_payload() for event in entry.events],
            }
            for entry in history
        ],
    }
