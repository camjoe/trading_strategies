from __future__ import annotations

import pytest

from paper_trading_web.backend.services.features.interpretation import interpret_signal


@pytest.mark.parametrize(
    ("strategy_id", "features", "expected"),
    [
        (
            "policy_regime",
            {"policy_risk_on_score": 0.61, "policy_defensive_tilt": 0.012},
            "Risk-on (bullish) — score 0.61, defensive tilt +0.012",
        ),
        (
            "policy_regime",
            {"policy_risk_on_score": 0.40},
            "Risk-off (bearish) — score 0.40",
        ),
        (
            "policy_regime",
            {},
            "No feature data",
        ),
        (
            "news_sentiment",
            {"news_sentiment_score": 0.22, "news_headline_count": 5},
            "Positive sentiment — score 0.220 (5 headlines)",
        ),
        (
            "news_sentiment",
            {"news_sentiment_score": -0.20},
            "Negative sentiment — score -0.200",
        ),
        (
            "social_trend_rotation",
            {"social_trend_score": 0.66, "social_mention_count": 8, "social_reddit_sentiment": 0.12},
            "Trend interest 66%, 8 Reddit mentions, Reddit sentiment +0.120",
        ),
        (
            "social_trend_rotation",
            {},
            "No trend data",
        ),
        (
            "unknown_strategy",
            {"foo": 1},
            "",
        ),
    ],
)
def test_interpret_signal(strategy_id: str, features: dict[str, float], expected: str) -> None:
    assert interpret_signal(strategy_id, features) == expected
