"""Promotion field vocabularies.

Closed value sets for the promotion data contracts' enumerated fields. Defined
as ``StrEnum`` so members are plain strings for SQLite/JSON round-tripping while
still giving type-checked, exhaustive vocabularies to domain policy.
"""

from __future__ import annotations

from enum import StrEnum


class PromotionStage(StrEnum):
    # Initial workflow stage before research evidence passes promotion gates.
    CANDIDATE = "candidate"
    # Research evidence is strong enough, but paper observation is still pending.
    RESEARCH_VALIDATED = "research_validated"
    # Paper evidence exists, but live-readiness blockers still remain.
    PAPER_OBSERVING = "paper_observing"
    # Automated checks passed and the strategy is ready for human promotion review.
    PROMOTION_REVIEW = "promotion_review"
    # Live trading is already enabled and promotion automation is no longer applicable.
    LIVE_ACTIVE = "live_active"


class PromotionStatus(StrEnum):
    # Automated promotion checks are currently blocked by missing or failing evidence.
    BLOCKED = "blocked"
    # Evidence collection is still in progress and human review is not ready yet.
    OBSERVING = "observing"
    # Automated checks passed; only a human review can approve live trading.
    READY_FOR_REVIEW = "ready_for_review"
    # The account is already live and remains under human control.
    LIVE = "live"


class PromotionReviewState(StrEnum):
    # Persisted promotion review has been requested and is awaiting operator action.
    REQUESTED = "requested"
    # Operator reviewed the request and approved it; live activation remains manual.
    APPROVED = "approved"
    # Operator reviewed the request and rejected it.
    REJECTED = "rejected"


class PromotionReviewEventType(StrEnum):
    # Initial persisted event when a promotion review request is created.
    REQUESTED = "requested"
    # Persisted event when an operator approves a promotion review request.
    APPROVED = "approved"
    # Persisted event when an operator rejects a promotion review request.
    REJECTED = "rejected"
    # Persisted event when an operator adds a note without changing the review state.
    NOTE_ADDED = "note_added"
