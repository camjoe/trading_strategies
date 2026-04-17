from __future__ import annotations

import sqlite3

from trading.services.promotion_service import (
    fetch_current_promotion_assessment,
    fetch_promotion_review_history,
)


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
    assessment = fetch_current_promotion_assessment(
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
        "history": [
            {
                "review": entry.review.to_payload(),
                "events": [event.to_payload() for event in entry.events],
            }
            for entry in history
        ],
    }
