"""Promotion service package.

This package is the stable public promotion surface. Concrete logic lives in
focused promotion modules beneath this package root.
"""

from __future__ import annotations

from trading.services.promotion.actions import (
    PROMOTION_REVIEW_ACTION_APPROVE,
    PROMOTION_REVIEW_ACTION_NOTE,
    PROMOTION_REVIEW_ACTION_REJECT,
    execute_promotion_review_action,
    execute_promotion_review_request,
)
from trading.services.promotion.assessment import (
    fetch_current_promotion_assessment,
    fetch_promotion_assessment,
)
from trading.services.promotion.history import (
    PromotionReviewHistoryEntry,
    fetch_promotion_review_history,
)
from trading.services.promotion.presentation import (
    render_promotion_review_history_lines,
    render_promotion_status_lines,
    show_promotion_review_history,
    show_promotion_status,
)

__all__ = [
    "PromotionReviewHistoryEntry",
    "PROMOTION_REVIEW_ACTION_APPROVE",
    "PROMOTION_REVIEW_ACTION_NOTE",
    "PROMOTION_REVIEW_ACTION_REJECT",
    "execute_promotion_review_action",
    "execute_promotion_review_request",
    "fetch_current_promotion_assessment",
    "fetch_promotion_assessment",
    "fetch_promotion_review_history",
    "render_promotion_review_history_lines",
    "render_promotion_status_lines",
    "show_promotion_review_history",
    "show_promotion_status",
]
