"""Promotion history queries for promotion consumers.

Owns persisted review-history reads beneath the stable
``trading.services.promotion`` package surface.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.promotion import PromotionReviewEvent, PromotionReviewRecord
from trading.repositories.promotion import PromotionReviewRepository
from trading.services.accounts.mutations import get_account
from trading.services.promotion.helpers import normalize_optional_text


@dataclass(frozen=True)
class PromotionReviewHistoryEntry:
    review: PromotionReviewRecord
    events: list[PromotionReviewEvent]


def _canonical_strategy_filter(strategy_name: str | None) -> str | None:
    """Canonicalize the strategy filter the way reviews are persisted.

    Reviews store the canonical name from ``validate_strategy_name``, so history
    must canonicalize the same way or a valid alias returns nothing (as the
    eligibility check already does). A blank name is no filter; an unresolvable
    name keeps its stripped form, which matches no canonical row.
    """
    stripped = normalize_optional_text(strategy_name)
    if stripped is None:
        return None
    try:
        return validate_strategy_name(stripped)
    except ValueError:
        return stripped


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
    repo = PromotionReviewRepository(conn)
    review_rows = repo.fetch_for_account(
        account_id=account.id,
        strategy_name=_canonical_strategy_filter(strategy_name),
        limit=limit,
    )
    return [
        PromotionReviewHistoryEntry(
            review=review,
            events=repo.fetch_events(review_id=review.id),
        )
        for review in review_rows
    ]


__all__ = [
    "PromotionReviewHistoryEntry",
    "fetch_promotion_review_history",
]
