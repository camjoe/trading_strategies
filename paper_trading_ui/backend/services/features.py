"""Alt-strategy feature-provider services.

Wraps the three alt-strategy providers (Policy, News, Social) and the
backtesting signal resolver so that route handlers never import directly
from ``trading.features.*`` or ``trading.backtesting.domain.*``.

Public API
----------
- ``get_provider_status(health_probe_ticker)`` — probe all three providers
  and return their status dicts (used by GET /api/features/status).
- ``get_signals(ticker)`` — compute feature-only signals for all three
  providers for the given ticker (used by POST /api/features/signals).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named thresholds — referenced in both _interpret_signal and _PROVIDER_META
# so that a threshold change only needs to happen in one place.
# ---------------------------------------------------------------------------

_POLICY_RISK_ON_BUY_THRESHOLD: float = 0.55
_POLICY_RISK_ON_SELL_THRESHOLD: float = 0.45
_NEWS_SENTIMENT_BUY_THRESHOLD: float = 0.10
_NEWS_SENTIMENT_SELL_THRESHOLD: float = -0.10

# Ticker used to probe each provider in the status endpoint.
_HEALTH_PROBE_TICKER = "SPY"

# Ordered list of (display_name, source_label_fallback, provider_class_name, strategy_id)
_PROVIDER_SPECS: list[tuple[str, str, str, str]] = [
    ("Policy", "etf-proxies", "PolicyFeatureProvider", "policy_regime"),
    ("News", "rss+vader", "NewsFeatureProvider", "news_sentiment"),
    ("Social", "reddit+gtrends", "SocialFeatureProvider", "social_trend_rotation"),
]

_PROVIDER_META: dict[str, dict] = {
    "Policy": {
        "description": (
            "Derives a macro/policy regime score from ETF price relatives over a 45-day "
            "lookback. Ticker-agnostic — the score reflects the broad market environment, "
            "not individual stock conditions."
        ),
        "data_sources": [
            "TLT – 20yr US Treasuries",
            "GLD – Gold",
            "XLU – Utilities",
            "UUP – USD Index ETF",
            "SPY – S&P 500",
        ],
        "feature_descriptions": {
            "policy_risk_on_score": {
                "label": "Risk-On Score",
                "description": (
                    f"0–1 composite; higher = risk-on (equities leading defensives). "
                    f"Buy threshold: ≥{_POLICY_RISK_ON_BUY_THRESHOLD}. "
                    f"Sell threshold: <{_POLICY_RISK_ON_SELL_THRESHOLD}."
                ),
                "range": "0–1",
            },
            "policy_defensive_tilt": {
                "label": "Defensive Tilt",
                "description": (
                    "Positive = defensives outperforming equities (risk-off). "
                    "Sell override when >0.02."
                ),
                "range": "–∞ to +∞ (typically ±0.05)",
            },
        },
        "signal_logic": (
            f"BUY when price > fast SMA > slow SMA AND "
            f"risk_on_score ≥ {_POLICY_RISK_ON_BUY_THRESHOLD} AND defensive_tilt ≤ 0.02. "
            f"SELL when price < slow SMA OR risk_on_score < {_POLICY_RISK_ON_SELL_THRESHOLD}."
        ),
    },
    "News": {
        "description": (
            "Scores recent ticker-specific news headlines with VADER sentiment analysis. "
            "Requires at least 3 scored headlines; falls back to hold when coverage is too thin."
        ),
        "data_sources": [
            "Yahoo Finance RSS",
            "Google News RSS",
            "NewsAPI (optional, requires NEWS_API_KEY)",
        ],
        "feature_descriptions": {
            "news_sentiment_score": {
                "label": "Sentiment Score",
                "description": (
                    f"Mean VADER compound score across recent headlines. "
                    f"+1 = maximally positive, −1 = maximally negative. "
                    f"Buy: ≥{_NEWS_SENTIMENT_BUY_THRESHOLD}. "
                    f"Sell: ≤{_NEWS_SENTIMENT_SELL_THRESHOLD}."
                ),
                "range": "−1 to +1",
            },
            "news_headline_count": {
                "label": "Headline Count",
                "description": (
                    "Number of headlines scored. "
                    "Signals require ≥3 headlines; fewer = hold regardless of sentiment."
                ),
                "range": "0 and up",
            },
        },
        "signal_logic": (
            f"BUY when price uptrend (close > fast SMA > slow SMA) AND "
            f"sentiment ≥ {_NEWS_SENTIMENT_BUY_THRESHOLD}. "
            f"SELL when price < fast SMA AND sentiment ≤ {_NEWS_SENTIMENT_SELL_THRESHOLD}."
        ),
    },
    "Social": {
        "description": (
            "Aggregates social signal strength from Google Trends interest (no API key) "
            "and Reddit post sentiment across r/stocks, r/investing, and r/wallstreetbets "
            "(requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)."
        ),
        "data_sources": [
            "Google Trends (pytrends)",
            "Reddit r/stocks",
            "Reddit r/investing",
            "Reddit r/wallstreetbets",
        ],
        "feature_descriptions": {
            "social_trend_score": {
                "label": "Trend Score",
                "description": (
                    "Google Trends 30-day interest index, normalised 0–1. "
                    "1.0 = peak search interest for this ticker. Buy threshold: ≥0.40."
                ),
                "range": "0–1",
            },
            "social_mention_count": {
                "label": "Reddit Mentions",
                "description": (
                    "Number of recent Reddit posts mentioning this ticker "
                    "across the tracked subreddits."
                ),
                "range": "0 and up",
            },
            "social_reddit_sentiment": {
                "label": "Reddit Sentiment",
                "description": (
                    "Mean VADER compound score of Reddit post titles. "
                    "+1 = fully positive. "
                    "Contributes to buy/sell threshold alongside trend score."
                ),
                "range": "−1 to +1",
            },
        },
        "signal_logic": (
            "BUY when trend_score ≥ 0.40 AND mention_count > 0 AND reddit_sentiment > 0. "
            "SELL when trend_score < 0.40 AND reddit_sentiment < 0."
        ),
    },
}


def _interpret_signal(strategy_id: str, features: dict) -> str:
    if strategy_id == "policy_regime":
        score = features.get("policy_risk_on_score")
        tilt = features.get("policy_defensive_tilt")
        if score is None:
            return "No feature data"
        if score >= _POLICY_RISK_ON_BUY_THRESHOLD:
            env = "Risk-on (bullish)"
        elif score < _POLICY_RISK_ON_SELL_THRESHOLD:
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
        if score >= _NEWS_SENTIMENT_BUY_THRESHOLD:
            sentiment = "Positive"
        elif score <= _NEWS_SENTIMENT_SELL_THRESHOLD:
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


def _build_unavailable_entry(name: str, source_label: str) -> dict[str, Any]:
    meta = _PROVIDER_META.get(name, {})
    return {
        "name": name,
        "source_label": source_label,
        "available": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "key_scores": {},
        "description": meta.get("description"),
        "data_sources": meta.get("data_sources"),
        "feature_descriptions": meta.get("feature_descriptions"),
        "signal_logic": meta.get("signal_logic"),
    }


def _load_providers() -> list[tuple[Any, str, str, str, str]]:
    """Lazily import and instantiate the three alt-strategy providers.

    Returns a list of ``(provider_or_None, display_name, source_label, strategy_id, class_name)``
    tuples. Each provider is instantiated independently so a single failure
    does not prevent the others from loading.
    """
    from trading.features.news_feature_provider import NewsFeatureProvider
    from trading.features.policy_feature_provider import PolicyFeatureProvider
    from trading.features.social_feature_provider import SocialFeatureProvider

    provider_classes = {
        "PolicyFeatureProvider": PolicyFeatureProvider,
        "NewsFeatureProvider": NewsFeatureProvider,
        "SocialFeatureProvider": SocialFeatureProvider,
    }

    result = []
    for display_name, source_label, class_name, strategy_id in _PROVIDER_SPECS:
        try:
            provider = provider_classes[class_name]()
        except Exception as exc:
            _LOG.warning("features: failed to init %s: %s", class_name, exc)
            provider = None
        result.append((provider, display_name, source_label, strategy_id, class_name))
    return result


def get_provider_status() -> list[dict[str, Any]]:
    """Probe all three alt-strategy feature providers and return their status.

    Uses ``SPY`` as the health-probe ticker.  Each entry includes rich
    metadata (description, data_sources, feature_descriptions, signal_logic)
    so the frontend can render explanatory provider cards without a second
    round-trip.
    """
    results: list[dict[str, Any]] = []
    for provider, name, label, _strategy_id, _class_name in _load_providers():
        if provider is None:
            results.append(_build_unavailable_entry(name, label))
            continue
        meta = _PROVIDER_META.get(name, {})
        try:
            bundle = provider.get_features(_HEALTH_PROBE_TICKER)
            results.append({
                "name": name,
                "source_label": provider.source_label,
                "available": bundle.available,
                "fetched_at": bundle.fetched_at.isoformat(),
                "key_scores": bundle.features if bundle.available else {},
                "description": meta.get("description"),
                "data_sources": meta.get("data_sources"),
                "feature_descriptions": meta.get("feature_descriptions"),
                "signal_logic": meta.get("signal_logic"),
            })
        except Exception as exc:
            _LOG.warning("features: status probe failed for %s: %s", name, exc)
            results.append(_build_unavailable_entry(name, label))
    return results


def get_signals(ticker: str) -> list[dict[str, Any]]:
    """Compute feature-only alt-strategy signals for *ticker*.

    Price history is not supplied, so momentum guards always fire and
    ``available`` is always ``False``.  The signals represent the raw
    feature-data direction only — suitable as contextual, not actionable,
    signals.
    """
    from trading.backtesting.domain.strategy_signals import resolve_signal

    empty_history = pd.Series([], dtype=float)
    signals: list[dict[str, Any]] = []

    for provider, name, _label, strategy_id, _class_name in _load_providers():
        meta = _PROVIDER_META.get(name, {})
        signal_logic = meta.get("signal_logic", "")
        feature_descriptions = meta.get("feature_descriptions")

        if provider is None:
            signals.append({
                "strategy": strategy_id,
                "signal": "hold",
                "available": False,
                "features": {},
                "signal_logic": signal_logic,
                "feature_descriptions": feature_descriptions,
                "interpretation": "",
            })
            continue

        try:
            bundle = provider.get_features(ticker)
        except Exception as exc:
            _LOG.warning("features: get_features failed for %s/%s: %s", strategy_id, ticker, exc)
            signals.append({
                "strategy": strategy_id,
                "signal": "hold",
                "available": False,
                "features": {},
                "signal_logic": signal_logic,
                "feature_descriptions": feature_descriptions,
                "interpretation": "",
            })
            continue

        if not bundle.available:
            signals.append({
                "strategy": strategy_id,
                "signal": "hold",
                "available": False,
                "features": {},
                "signal_logic": signal_logic,
                "feature_descriptions": feature_descriptions,
                "interpretation": "",
            })
            continue

        try:
            signal = resolve_signal(strategy_id, empty_history, bundle.to_feature_row())
        except Exception as exc:
            _LOG.warning("features: signal fn failed for %s/%s: %s", strategy_id, ticker, exc)
            signal = "hold"

        signals.append({
            "strategy": strategy_id,
            "signal": signal,
            "available": False,
            "reason": "no_price_history",
            "features": bundle.features,
            "signal_logic": signal_logic,
            "feature_descriptions": feature_descriptions,
            "interpretation": _interpret_signal(strategy_id, bundle.features),
        })

    return signals
