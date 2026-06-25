from __future__ import annotations

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
