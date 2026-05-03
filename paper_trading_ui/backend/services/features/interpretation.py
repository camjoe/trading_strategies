from __future__ import annotations

from .shared import (
    NEWS_SENTIMENT_BUY_THRESHOLD,
    NEWS_SENTIMENT_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_RISK_ON_SELL_THRESHOLD,
)


def interpret_signal(strategy_id: str, features: dict) -> str:
    if strategy_id == "policy_regime":
        score = features.get("policy_risk_on_score")
        tilt = features.get("policy_defensive_tilt")
        if score is None:
            return "No feature data"
        if score >= POLICY_RISK_ON_BUY_THRESHOLD:
            env = "Risk-on (bullish)"
        elif score < POLICY_RISK_ON_SELL_THRESHOLD:
            env = "Risk-off (bearish)"
        else:
            env = "Neutral"
        tilt_note = f", defensive tilt {tilt:+.3f}" if tilt is not None else ""
        return f"{env} — score {score:.2f}{tilt_note}"

    if strategy_id == "news_sentiment":
        score = features.get("news_sentiment_score")
        count = features.get("news_headline_count")
        if score is None:
            return "No headlines"
        if score >= NEWS_SENTIMENT_BUY_THRESHOLD:
            sentiment = "Positive"
        elif score <= NEWS_SENTIMENT_SELL_THRESHOLD:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
        count_note = f" ({int(count)} headlines)" if count is not None else ""
        return f"{sentiment} sentiment — score {score:.3f}{count_note}"

    if strategy_id == "social_trend_rotation":
        trend = features.get("social_trend_score")
        mentions = features.get("social_mention_count")
        reddit = features.get("social_reddit_sentiment")
        if trend is None:
            return "No trend data"
        interest = f"Trend interest {trend:.0%}"
        mention_note = f", {int(mentions)} Reddit mentions" if mentions is not None else ""
        sentiment_note = f", Reddit sentiment {reddit:+.3f}" if reddit is not None else ""
        return f"{interest}{mention_note}{sentiment_note}"

    return ""
