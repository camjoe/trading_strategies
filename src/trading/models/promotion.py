"""Strategy-promotion data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_int, row_json_object
from trading.models.evaluation import BacktestFreshness


def _optional_text(values: Mapping[str, object], key: str) -> str | None:
    """Read a nullable text column, treating the empty string as absent.

    The writer stores ``""`` where a caller passed None, so the read side has to
    invert that or a cleared note comes back as an empty string.
    """
    value = values[key]
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_review_state(values: Mapping[str, object], key: str) -> PromotionReviewState | None:
    text = _optional_text(values, key)
    return None if text is None else PromotionReviewState(text)


# Current schema label for the initial promotion assessment slice.
PROMOTION_ASSESSMENT_VERSION = "phase4.v1"

# Current actor type label for operator-initiated review events.
# Single value today; promote to a StrEnum once a second actor type exists.
PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR = "operator"


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


# --- Assessment ---


@dataclass(frozen=True)
class PromotionAssessment:
    version: str = PROMOTION_ASSESSMENT_VERSION
    account_name: str | None = None
    strategy_name: str | None = None
    evaluation_generated_at: str | None = None
    stage: PromotionStage = PromotionStage.CANDIDATE
    status: PromotionStatus = PromotionStatus.BLOCKED
    ready_for_live: bool = False
    live_trading_enabled: bool = False
    overall_confidence: float = 0.0
    # Advisory backtest staleness carried through from the evaluation artifact.
    backtest_freshness: BacktestFreshness | None = None
    data_gaps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: str | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


# --- Review workflow ---


@dataclass(frozen=True)
class PromotionReviewRecord:
    # Required: a *Record* is materialized from a persisted row, which always has
    # an id. Defaulting it to None made every caller coerce with int(review.id)
    # to get back a value the row had all along.
    id: int
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

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> PromotionReviewRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            account_name_snapshot=row_expect_str(values, "account_name_snapshot"),
            strategy_id=row_int(values, "strategy_id"),
            strategy_name=row_expect_str(values, "strategy_name"),
            review_state=PromotionReviewState(row_expect_str(values, "review_state")),
            assessment_stage=PromotionStage(row_expect_str(values, "assessment_stage")),
            assessment_status=PromotionStatus(row_expect_str(values, "assessment_status")),
            ready_for_live=bool(row_expect_int(values, "ready_for_live")),
            overall_confidence=row_expect_float(values, "overall_confidence"),
            live_trading_enabled_snapshot=bool(row_expect_int(values, "live_trading_enabled_snapshot")),
            promotion_assessment_version=row_expect_str(values, "promotion_assessment_version"),
            evaluation_artifact_version=row_expect_str(values, "evaluation_artifact_version"),
            frozen_assessment_payload=row_json_object(values, "frozen_assessment_payload"),
            frozen_evaluation_payload=row_json_object(values, "frozen_evaluation_payload"),
            requested_by=_optional_text(values, "requested_by"),
            reviewed_by=_optional_text(values, "reviewed_by"),
            operator_summary_note=_optional_text(values, "operator_summary_note"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
            closed_at=_optional_text(values, "closed_at"),
        )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionReviewEvent:
    id: int | None = None
    review_id: int | None = None
    event_seq: int = 0
    event_type: PromotionReviewEventType = PromotionReviewEventType.REQUESTED
    actor_type: str = PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR
    actor_name: str | None = None
    from_review_state: PromotionReviewState | None = None
    to_review_state: PromotionReviewState | None = None
    note: str | None = None
    event_payload: dict[str, object] = field(default_factory=dict)
    created_at: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> PromotionReviewEvent:
        return cls(
            id=row_expect_int(values, "id"),
            review_id=row_expect_int(values, "review_id"),
            event_seq=row_expect_int(values, "event_seq"),
            event_type=PromotionReviewEventType(row_expect_str(values, "event_type")),
            actor_type=row_expect_str(values, "actor_type"),
            actor_name=_optional_text(values, "actor_name"),
            from_review_state=_optional_review_state(values, "from_review_state"),
            to_review_state=_optional_review_state(values, "to_review_state"),
            note=_optional_text(values, "note"),
            event_payload=row_json_object(values, "event_payload"),
            created_at=row_expect_str(values, "created_at"),
        )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
