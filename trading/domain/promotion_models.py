from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Current schema label for the initial promotion assessment slice.
PROMOTION_ASSESSMENT_VERSION = "phase4.v1"

# Initial workflow stage before research evidence passes promotion gates.
PROMOTION_STAGE_CANDIDATE = "candidate"

# Research evidence is strong enough, but paper observation is still pending.
PROMOTION_STAGE_RESEARCH_VALIDATED = "research_validated"

# Paper evidence exists, but live-readiness blockers still remain.
PROMOTION_STAGE_PAPER_OBSERVING = "paper_observing"

# Automated checks passed and the strategy is ready for human promotion review.
PROMOTION_STAGE_PROMOTION_REVIEW = "promotion_review"

# Live trading is already enabled and promotion automation is no longer applicable.
PROMOTION_STAGE_LIVE_ACTIVE = "live_active"

# Automated promotion checks are currently blocked by missing or failing evidence.
PROMOTION_STATUS_BLOCKED = "blocked"

# Evidence collection is still in progress and human review is not ready yet.
PROMOTION_STATUS_OBSERVING = "observing"

# Automated checks passed; only a human review can approve live trading.
PROMOTION_STATUS_READY_FOR_REVIEW = "ready_for_review"

# The account is already live and remains under human control.
PROMOTION_STATUS_LIVE = "live"


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
