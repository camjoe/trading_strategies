from __future__ import annotations

from dataclasses import asdict, dataclass, field

from trading.models.promotion.constants import (
    PROMOTION_ASSESSMENT_VERSION,
    PROMOTION_STAGE_CANDIDATE,
    PROMOTION_STATUS_BLOCKED,
)


@dataclass(frozen=True)
class PromotionAssessment:
    version: str = PROMOTION_ASSESSMENT_VERSION
    account_name: str | None = None
    strategy_name: str | None = None
    evaluation_generated_at: str | None = None
    stage: str = PROMOTION_STAGE_CANDIDATE
    status: str = PROMOTION_STATUS_BLOCKED
    ready_for_live: bool = False
    live_trading_enabled: bool = False
    overall_confidence: float = 0.0
    data_gaps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: str | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
