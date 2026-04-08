"""trading_bridge — single seam between backtesting and the rest of trading/.

Every symbol that backtesting/ borrows from trading/ is imported here and
re-exported.  When backtesting moves to a top-level package, only this file
needs updating — internal backtesting modules stay unchanged.

If trading/features/ is ever moved under backtesting/, the three feature-
provider blocks below can be deleted entirely.
"""

from trading.services.accounts_service import get_account
from trading.domain.rotation import resolve_active_strategy
from trading.domain.returns import safe_return_pct
from trading.utils.coercion import (
    coerce_float,
    row_expect_float,
    row_expect_int,
    row_expect_str,
    row_float,
    row_str,
)

# Feature provider constants consumed by backtesting/domain/strategy_signals.py.
from trading.features.policy_feature_provider import (
    POLICY_DEFENSIVE_TILT,
    POLICY_MAX_DEFENSIVE_TILT,
    POLICY_RISK_OFF_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_RISK_ON_SCORE,
)
from trading.features.news_feature_provider import (
    NEWS_BUY_SENTIMENT_THRESHOLD,
    NEWS_HEADLINE_COUNT,
    NEWS_MIN_HEADLINES_REQUIRED,
    NEWS_SELL_SENTIMENT_THRESHOLD,
    NEWS_SENTIMENT_SCORE,
)
from trading.features.social_feature_provider import (
    SOCIAL_MENTION_COUNT,
    SOCIAL_MIN_REDDIT_SENTIMENT,
    SOCIAL_REDDIT_SENTIMENT,
    SOCIAL_TREND_BUY_THRESHOLD,
    SOCIAL_TREND_EXIT_THRESHOLD,
    SOCIAL_TREND_SCORE,
)

__all__ = [
    # accounts
    "get_account",
    # domain
    "resolve_active_strategy",
    "safe_return_pct",
    # coercion
    "coerce_float",
    "row_expect_float",
    "row_expect_int",
    "row_expect_str",
    "row_float",
    "row_str",
    # policy feature constants
    "POLICY_DEFENSIVE_TILT",
    "POLICY_MAX_DEFENSIVE_TILT",
    "POLICY_RISK_OFF_SELL_THRESHOLD",
    "POLICY_RISK_ON_BUY_THRESHOLD",
    "POLICY_RISK_ON_SCORE",
    # news feature constants
    "NEWS_BUY_SENTIMENT_THRESHOLD",
    "NEWS_HEADLINE_COUNT",
    "NEWS_MIN_HEADLINES_REQUIRED",
    "NEWS_SELL_SENTIMENT_THRESHOLD",
    "NEWS_SENTIMENT_SCORE",
    # social feature constants
    "SOCIAL_MENTION_COUNT",
    "SOCIAL_MIN_REDDIT_SENTIMENT",
    "SOCIAL_REDDIT_SENTIMENT",
    "SOCIAL_TREND_BUY_THRESHOLD",
    "SOCIAL_TREND_EXIT_THRESHOLD",
    "SOCIAL_TREND_SCORE",
]
