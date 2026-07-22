from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

_LOG = logging.getLogger(__name__)

# Named thresholds reused by metadata and interpretation logic.
POLICY_RISK_ON_BUY_THRESHOLD: float = 0.55
POLICY_RISK_ON_SELL_THRESHOLD: float = 0.45
NEWS_SENTIMENT_BUY_THRESHOLD: float = 0.10
NEWS_SENTIMENT_SELL_THRESHOLD: float = -0.10

# Ticker used to probe each provider in the status endpoint.
HEALTH_PROBE_TICKER = "SPY"

# Ordered list of (display_name, source_label_fallback, provider_class_name, strategy_id)
PROVIDER_SPECS: list[tuple[str, str, str, str]] = [
    ("Policy", "etf-proxies", "PolicyFeatureProvider", "policy_regime"),
    ("News", "rss+vader", "NewsFeatureProvider", "news_sentiment"),
    ("Social", "reddit+gtrends", "SocialFeatureProvider", "social_trend_rotation"),
]

PROVIDER_META: dict[str, dict[str, Any]] = {
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
                    f"Buy threshold: ≥{POLICY_RISK_ON_BUY_THRESHOLD}. "
                    f"Sell threshold: <{POLICY_RISK_ON_SELL_THRESHOLD}."
                ),
                "range": "0–1",
            },
            "policy_defensive_tilt": {
                "label": "Defensive Tilt",
                "description": ("Positive = defensives outperforming equities (risk-off). Sell override when >0.02."),
                "range": "–∞ to +∞ (typically ±0.05)",
            },
        },
        "signal_logic": (
            f"BUY when price > fast SMA > slow SMA AND "
            f"risk_on_score ≥ {POLICY_RISK_ON_BUY_THRESHOLD} AND defensive_tilt ≤ 0.02. "
            f"SELL when price < slow SMA OR risk_on_score < {POLICY_RISK_ON_SELL_THRESHOLD}."
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
                    f"Buy: ≥{NEWS_SENTIMENT_BUY_THRESHOLD}. "
                    f"Sell: ≤{NEWS_SENTIMENT_SELL_THRESHOLD}."
                ),
                "range": "−1 to +1",
            },
            "news_headline_count": {
                "label": "Headline Count",
                "description": (
                    "Number of headlines scored. Signals require ≥3 headlines; fewer = hold regardless of sentiment."
                ),
                "range": "0 and up",
            },
        },
        "signal_logic": (
            f"BUY when price uptrend (close > fast SMA > slow SMA) AND "
            f"sentiment ≥ {NEWS_SENTIMENT_BUY_THRESHOLD}. "
            f"SELL when price < fast SMA AND sentiment ≤ {NEWS_SENTIMENT_SELL_THRESHOLD}."
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
                "description": ("Number of recent Reddit posts mentioning this ticker across the tracked subreddits."),
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


def external_features_disabled() -> bool:
    """Return whether network-backed feature providers are administratively disabled."""
    return os.getenv("TRADING_EXTERNAL_FEATURES_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def build_unavailable_entry(name: str, source_label: str) -> dict[str, Any]:
    meta = PROVIDER_META.get(name, {})
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


def load_providers() -> list[tuple[Any, str, str, str, str]]:
    """Lazily import and instantiate the three alt-strategy providers.

    Returns a list of ``(provider_or_none, display_name, source_label, strategy_id, class_name)``
    tuples. Providers initialize independently so one failure does not block others.
    """
    if external_features_disabled():
        return [
            (None, name, label, strategy_id, class_name) for name, label, class_name, strategy_id in PROVIDER_SPECS
        ]

    from infrastructure.feature_providers.news_provider import NewsFeatureProvider
    from infrastructure.feature_providers.policy_provider import PolicyFeatureProvider
    from infrastructure.feature_providers.social_provider import SocialFeatureProvider

    provider_classes = {
        "PolicyFeatureProvider": PolicyFeatureProvider,
        "NewsFeatureProvider": NewsFeatureProvider,
        "SocialFeatureProvider": SocialFeatureProvider,
    }

    loaded: list[tuple[Any, str, str, str, str]] = []
    for display_name, source_label, class_name, strategy_id in PROVIDER_SPECS:
        try:
            provider = provider_classes[class_name]()
        except Exception as exc:
            _LOG.warning("features: failed to init %s: %s", class_name, exc)
            provider = None
        loaded.append((provider, display_name, source_label, strategy_id, class_name))
    return loaded
