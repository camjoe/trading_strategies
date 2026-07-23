from __future__ import annotations

import math

import pandas as pd

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
from trading.domain.strategies.contracts import StrategyParams

# Minimum fraction of available proxy data required to trust a topic-proxy feature signal
PROXY_AVAILABILITY_THRESHOLD = 0.5


def _feature_value(feature_history: pd.DataFrame | None, column: str) -> float | None:
    if feature_history is None or feature_history.empty or column not in feature_history.columns:
        return None
    series = pd.to_numeric(feature_history[column], errors="coerce").dropna()
    if series.empty:
        return None
    val = float(series.iloc[-1])
    # Treat non-finite feature values (inf/-inf) as unavailable so signal
    # logic never makes decisions based on unbounded inputs.
    return val if math.isfinite(val) else None


def _topic_proxy_rotation_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    min_history = max(40, window)
    if len(history) < min_history:
        return "hold"

    proxy_available = _feature_value(feature_history, "topic_proxy_available")
    rel_strength = _feature_value(feature_history, "topic_proxy_rel_strength")
    trend_gap = _feature_value(feature_history, "topic_proxy_trend_gap")
    if (
        proxy_available is None
        or proxy_available < PROXY_AVAILABILITY_THRESHOLD
        or rel_strength is None
        or trend_gap is None
    ):
        return "hold"

    close = float(history.iloc[-1])
    sma_mid = float(history.tail(window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_mid):
        return "hold"
    min_rel_strength = float(params.get("min_rel_strength", 0.0))
    exit_rel_strength = float(params.get("exit_rel_strength", 0.0))
    min_proxy_trend_gap = float(params.get("min_proxy_trend_gap", 0.0))

    if close > sma_mid and rel_strength > min_rel_strength and trend_gap > min_proxy_trend_gap:
        return "buy"
    if close < sma_mid or rel_strength < exit_rel_strength or trend_gap < 0.0:
        return "sell"
    return "hold"


def _macro_proxy_regime_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    min_history = max(60, slow_window)
    if len(history) < min_history:
        return "hold"

    risk_on_score = _feature_value(feature_history, "macro_risk_on_score")
    vix_pressure = _feature_value(feature_history, "macro_vix_pressure")
    equity_bond_spread = _feature_value(feature_history, "macro_equity_bond_spread")
    if risk_on_score is None or vix_pressure is None or equity_bond_spread is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"
    min_risk_on_score = float(params.get("min_risk_on_score", 0.0))
    min_equity_bond_spread = float(params.get("min_equity_bond_spread", 0.0))
    max_vix_pressure = float(params.get("max_vix_pressure", 0.12))
    exit_risk_on_score = float(params.get("exit_risk_on_score", 0.0))

    price_trend_is_bullish = close > sma_fast > sma_slow
    risk_on_score_is_strong_enough = risk_on_score >= min_risk_on_score
    equity_bond_spread_is_strong_enough = equity_bond_spread >= min_equity_bond_spread
    vix_pressure_is_within_limit = vix_pressure <= max_vix_pressure
    has_macro_buy_setup = (
        price_trend_is_bullish
        and risk_on_score_is_strong_enough
        and equity_bond_spread_is_strong_enough
        and vix_pressure_is_within_limit
    )
    if has_macro_buy_setup:
        return "buy"
    should_exit_macro_regime = (
        close < sma_fast or risk_on_score < exit_risk_on_score or vix_pressure > max_vix_pressure
    )
    if should_exit_macro_regime:
        return "sell"
    return "hold"


def _policy_regime_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Policy regime signal using ETF-derived macro/political environment indicators.

    Buys when price momentum aligns with a risk-on macro environment (SPY
    outperforming defensive ETFs).  Falls back to ``"hold"`` when features
    from :class:`~features.policy_feature_provider.PolicyFeatureProvider`
    are unavailable.

    Required features (from ``feature_history``):
        policy_risk_on_score   — 0–1 composite risk-on score (higher = risk-on).
        policy_defensive_tilt  — Positive when defensives outperform equities.
    """
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    if len(history) < max(30, slow_window):
        return "hold"

    risk_on_score = _feature_value(feature_history, POLICY_RISK_ON_SCORE)
    defensive_tilt = _feature_value(feature_history, POLICY_DEFENSIVE_TILT)
    if risk_on_score is None or defensive_tilt is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"

    risk_on_threshold = float(params.get("risk_on_threshold", POLICY_RISK_ON_BUY_THRESHOLD))
    risk_off_threshold = float(params.get("risk_off_threshold", POLICY_RISK_OFF_SELL_THRESHOLD))
    max_defensive_tilt = float(params.get("max_defensive_tilt", POLICY_MAX_DEFENSIVE_TILT))

    price_trend_is_bullish = close > sma_fast > sma_slow
    risk_on_score_is_strong_enough = risk_on_score >= risk_on_threshold
    defensive_tilt_is_within_limit = defensive_tilt <= max_defensive_tilt
    has_policy_buy_setup = price_trend_is_bullish and risk_on_score_is_strong_enough and defensive_tilt_is_within_limit
    if has_policy_buy_setup:
        return "buy"
    if close < sma_slow or risk_on_score < risk_off_threshold:
        return "sell"
    return "hold"


def _news_sentiment_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """News sentiment signal using VADER-scored headlines.

    Buys when price is in a short-term uptrend and recent news sentiment
    is bullish.  Sells when sentiment turns negative and price is below
    the short SMA.  Falls back to ``"hold"`` when features from
    :class:`~features.news_feature_provider.NewsFeatureProvider`
    are unavailable or headline volume is too low.

    Required features (from ``feature_history``):
        news_sentiment_score  — Mean VADER compound score in [-1, 1].
        news_headline_count   — Number of headlines scored.
    """
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 30))
    if len(history) < max(10, slow_window):
        return "hold"

    sentiment = _feature_value(feature_history, NEWS_SENTIMENT_SCORE)
    headline_count = _feature_value(feature_history, NEWS_HEADLINE_COUNT)
    if sentiment is None or headline_count is None:
        return "hold"

    min_headlines = float(params.get("min_headlines", NEWS_MIN_HEADLINES_REQUIRED))
    if headline_count < min_headlines:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"

    buy_sentiment = float(params.get("buy_sentiment", NEWS_BUY_SENTIMENT_THRESHOLD))
    sell_sentiment = float(params.get("sell_sentiment", NEWS_SELL_SENTIMENT_THRESHOLD))

    if close > sma_fast > sma_slow and sentiment >= buy_sentiment:
        return "buy"
    if close < sma_fast and sentiment <= sell_sentiment:
        return "sell"
    return "hold"


def _social_trend_rotation_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Social trend rotation signal using Google Trends interest and Reddit mentions.

    Buys when the ticker shows elevated social interest (Google Trends score)
    alongside positive Reddit sentiment and an upward price trend.  Sells
    when social interest is fading and price weakens.  Falls back to
    ``"hold"`` when features from
    :class:`~features.social_feature_provider.SocialFeatureProvider`
    are unavailable.

    Required features (from ``feature_history``):
        social_trend_score      — Google Trends interest, normalised [0, 1].
        social_mention_count    — Reddit post count (float).
        social_reddit_sentiment — Mean VADER score of Reddit titles [-1, 1].
    """
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 30))
    if len(history) < max(10, slow_window):
        return "hold"

    trend_score = _feature_value(feature_history, SOCIAL_TREND_SCORE)
    mention_count = _feature_value(feature_history, SOCIAL_MENTION_COUNT)
    reddit_sentiment = _feature_value(feature_history, SOCIAL_REDDIT_SENTIMENT)
    if trend_score is None or mention_count is None or reddit_sentiment is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if not math.isfinite(close) or not math.isfinite(sma_fast) or not math.isfinite(sma_slow):
        return "hold"

    trend_threshold = float(params.get("trend_threshold", SOCIAL_TREND_BUY_THRESHOLD))
    trend_exit = float(params.get("trend_exit", SOCIAL_TREND_EXIT_THRESHOLD))
    min_reddit_sentiment = float(params.get("min_reddit_sentiment", SOCIAL_MIN_REDDIT_SENTIMENT))

    price_trend_is_bullish = close > sma_fast > sma_slow
    trend_score_is_strong_enough = trend_score >= trend_threshold
    reddit_sentiment_is_strong_enough = reddit_sentiment >= min_reddit_sentiment
    has_social_buy_setup = (
        price_trend_is_bullish and trend_score_is_strong_enough and reddit_sentiment_is_strong_enough
    )
    if has_social_buy_setup:
        return "buy"
    if close < sma_slow or trend_score < trend_exit:
        return "sell"
    return "hold"
