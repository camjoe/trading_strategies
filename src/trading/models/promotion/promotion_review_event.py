from __future__ import annotations

from dataclasses import asdict, dataclass, field

from trading.models.promotion.constants import (
    PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR,
    PROMOTION_REVIEW_EVENT_REQUESTED,
)


@dataclass(frozen=True)
class PromotionReviewEvent:
    id: int | None = None
    review_id: int | None = None
    event_seq: int = 0
    event_type: str = PROMOTION_REVIEW_EVENT_REQUESTED
    actor_type: str = PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR
    actor_name: str | None = None
    from_review_state: str | None = None
    to_review_state: str | None = None
    note: str | None = None
    event_payload: dict[str, object] = field(default_factory=dict)
    created_at: str | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
