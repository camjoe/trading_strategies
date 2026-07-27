"""Read-only promotion-eligibility checks for other services (e.g. rotation)."""

from __future__ import annotations

import sqlite3

from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.promotion.enums import PromotionReviewState
from trading.repositories.promotion import PromotionReviewRepository


def is_strategy_approved_for_live(conn: sqlite3.Connection, *, account_id: int, strategy_name: str) -> bool:
    """Whether the strategy's most recent promotion review for this account is approved.

    Only the latest review governs: a strategy with no review, or whose latest
    review was requested/rejected, is not approved — a later request
    supersedes an earlier approval. Callers (e.g. a book's rotation schedule)
    may hold an operator-typed alias rather than the canonical strategy id
    promotion review requests are always persisted under
    (``execute_promotion_review_request`` resolves via the same
    ``validate_strategy_name``), so this canonicalizes before querying. An
    unresolvable name is treated as not approved rather than raising — a
    stale/malformed schedule entry should degrade to ineligible, not crash the
    rotation run.
    """
    try:
        canonical_strategy_name = validate_strategy_name(strategy_name)
    except ValueError:
        return False
    reviews = PromotionReviewRepository(conn).fetch_for_account(
        account_id=account_id, strategy_name=canonical_strategy_name, limit=1
    )
    return bool(reviews) and reviews[0].review_state == PromotionReviewState.APPROVED


__all__ = ["is_strategy_approved_for_live"]
