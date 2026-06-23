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

# Persisted promotion review has been requested and is awaiting operator action.
PROMOTION_REVIEW_STATE_REQUESTED = "requested"

# Operator reviewed the request and approved it; live activation remains manual.
PROMOTION_REVIEW_STATE_APPROVED = "approved"

# Operator reviewed the request and rejected it.
PROMOTION_REVIEW_STATE_REJECTED = "rejected"

# Initial persisted event when a promotion review request is created.
PROMOTION_REVIEW_EVENT_REQUESTED = "requested"

# Persisted event when an operator approves a promotion review request.
PROMOTION_REVIEW_EVENT_APPROVED = "approved"

# Persisted event when an operator rejects a promotion review request.
PROMOTION_REVIEW_EVENT_REJECTED = "rejected"

# Persisted event when an operator adds a note without changing the review state.
PROMOTION_REVIEW_EVENT_NOTE_ADDED = "note_added"

# Current actor type label for operator-initiated review events.
PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR = "operator"


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


@dataclass(frozen=True)
class PromotionReviewRecord:
    id: int | None = None
    account_id: int | None = None
    account_name_snapshot: str | None = None
    strategy_name: str | None = None
    review_state: str = PROMOTION_REVIEW_STATE_REQUESTED
    assessment_stage: str = PROMOTION_STAGE_CANDIDATE
    assessment_status: str = PROMOTION_STATUS_BLOCKED
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
