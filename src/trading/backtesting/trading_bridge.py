"""trading_bridge — single seam between backtesting and the rest of trading/."""

from __future__ import annotations

from trading.domain.feature_provider import (
    NEWS_BUY_SENTIMENT_THRESHOLD,
    NEWS_HEADLINE_COUNT,
    NEWS_MIN_HEADLINES_REQUIRED,
    NEWS_SELL_SENTIMENT_THRESHOLD,
    NEWS_SENTIMENT_SCORE,
    POLICY_DEFENSIVE_TILT,
    POLICY_MAX_DEFENSIVE_TILT,
    POLICY_RISK_OFF_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_RISK_ON_SCORE,
    SOCIAL_MENTION_COUNT,
    SOCIAL_MIN_REDDIT_SENTIMENT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_BUY_THRESHOLD,
    SOCIAL_TREND_EXIT_THRESHOLD,
    SOCIAL_TREND_SCORE,
)
from trading.services.accounts import get_account
from trading.domain.returns import safe_return_pct


def active_strategy_for_account(conn, account_id: int, *, fallback: str) -> str:
    """The default-book assignment's strategy (ADR 014), account fallback.

    Deferred import: services.books reaches back through services.evaluation
    into backtesting repositories at package-init time.
    """
    from trading.services.books.book_assignments import active_strategy_for_account as _impl

    return _impl(conn, account_id, fallback=fallback)


__all__ = [
    "get_account",
    "active_strategy_for_account",
    "safe_return_pct",
    "POLICY_DEFENSIVE_TILT",
    "POLICY_MAX_DEFENSIVE_TILT",
    "POLICY_RISK_OFF_SELL_THRESHOLD",
    "POLICY_RISK_ON_BUY_THRESHOLD",
    "POLICY_RISK_ON_SCORE",
    "NEWS_BUY_SENTIMENT_THRESHOLD",
    "NEWS_HEADLINE_COUNT",
    "NEWS_MIN_HEADLINES_REQUIRED",
    "NEWS_SELL_SENTIMENT_THRESHOLD",
    "NEWS_SENTIMENT_SCORE",
    "SOCIAL_MENTION_COUNT",
    "SOCIAL_MIN_REDDIT_SENTIMENT",
    "SOCIAL_REDDIT_SENTIMENT",
    "SOCIAL_TREND_BUY_THRESHOLD",
    "SOCIAL_TREND_EXIT_THRESHOLD",
    "SOCIAL_TREND_SCORE",
]
