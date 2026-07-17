from __future__ import annotations

from dataclasses import asdict, dataclass, field

from trading.models.promotion.constants import PROMOTION_ASSESSMENT_VERSION
from trading.models.promotion.enums import PromotionReviewState, PromotionStage, PromotionStatus


@dataclass(frozen=True)
class PromotionReviewRecord:
    id: int | None = None
    account_id: int | None = None
    account_name_snapshot: str | None = None
    # strategy_id is the real strategies FK (revision 0007); strategy_name is
    # the display snapshot, mirroring account_id + account_name_snapshot.
    strategy_id: int | None = None
    strategy_name: str | None = None
    review_state: PromotionReviewState = PromotionReviewState.REQUESTED
    assessment_stage: PromotionStage = PromotionStage.CANDIDATE
    assessment_status: PromotionStatus = PromotionStatus.BLOCKED
    ready_for_live: bool = False
    overall_confidence: float = 0.0
    live_trading_enabled_snapshot: bool = False
    promotion_assessment_version: str = PROMOTION_ASSESSMENT_VERSION
    evaluation_artifact_version: str | None = None
    frozen_assessment_payload: dict[str, object] = field(default_factory=dict)
    frozen_evaluation_payload: dict[str, object] = field(default_factory=dict)
    requested_by: str | None = None
    reviewed_by: str | None = None
    operator_summary_note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
