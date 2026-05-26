"""Promotion history queries for promotion consumers.

Owns persisted review-history reads beneath the stable
``trading.services.promotion`` package surface.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from trading.domain.promotion_models import PromotionReviewEvent, PromotionReviewRecord
from trading.repositories.promotion import (
    fetch_promotion_review_events,
    fetch_promotion_reviews_for_account,
)
from trading.services.accounts import get_account
from trading.services.promotion.helpers import normalize_optional_text


@dataclass(frozen=True)
class PromotionReviewHistoryEntry:
    review: PromotionReviewRecord
    events: list[PromotionReviewEvent]


def fetch_promotion_review_history(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
    limit: int = 10,
) -> list[PromotionReviewHistoryEntry]:
    if limit <= 0:
        raise ValueError("Promotion review history limit must be positive.")
    account = get_account(conn, account_name)
    review_rows = fetch_promotion_reviews_for_account(
        conn,
        account_id=account.id,
        strategy_name=normalize_optional_text(strategy_name),
        limit=limit,
    )
    return [
        PromotionReviewHistoryEntry(
            review=review,
            events=fetch_promotion_review_events(conn, review_id=int(review.id)),
        )
        for review in review_rows
    ]


__all__ = [
    "PromotionReviewHistoryEntry",
    "fetch_promotion_review_history",
]
