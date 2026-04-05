"""Feature-provider status and alt-strategy signal endpoints.

GET  /api/features/status  — health probe all three alt-strategy providers
POST /api/features/signals — run alt-strategy signals for a given ticker
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter

from ..schemas import FeatureSignalsRequest

_LOG = logging.getLogger(__name__)

router = APIRouter()

# Ticker used to probe each provider in the status endpoint.
_HEALTH_PROBE_TICKER = "SPY"

# Ordered list of (display_name, source_label_fallback, provider_factory, signal_fn_name)
# Provider instantiation and signal calls are lazy so failures degrade gracefully.
_PROVIDER_SPECS: list[tuple[str, str, str, str]] = [
    ("Policy", "etf-proxies", "PolicyFeatureProvider", "policy_regime"),
    ("News", "rss+vader", "NewsFeatureProvider", "news_sentiment"),
    ("Social", "reddit+gtrends", "SocialFeatureProvider", "social_trend_rotation"),
]

_PROVIDER_META: dict[str, dict] = {
    "Policy": {
        "description": "Derives a macro/policy regime score from ETF price relatives over a 45-day lookback. Ticker-agnostic — the score reflects the broad market environment, not individual stock conditions.",
        "data_sources": ["TLT – 20yr US Treasuries", "GLD – Gold", "XLU – Utilities", "UUP – USD Index ETF", "SPY – S&P 500"],
        "feature_descriptions": {
            "policy_risk_on_score": {
                "label": "Risk-On Score",
                "description": "0–1 composite; higher = risk-on (equities leading defensives). Buy threshold: ≥0.55. Sell threshold: <0.45.",
                "range": "0–1",
            },
            "policy_defensive_tilt": {
                "label": "Defensive Tilt",
                "description": "Positive = defensives outperforming equities (risk-off). Sell override when >0.02.",
                "range": "–∞ to +∞ (typically ±0.05)",
            },
        },
        "signal_logic": "BUY when price > fast SMA > slow SMA AND risk_on_score ≥ 0.55 AND defensive_tilt ≤ 0.02. SELL when price < slow SMA OR risk_on_score < 0.45.",
    },
    "News": {
        "description": "Scores recent ticker-specific news headlines with VADER sentiment analysis. Requires at least 3 scored headlines; falls back to hold when coverage is too thin.",
        "data_sources": ["Yahoo Finance RSS", "Google News RSS", "NewsAPI (optional, requires NEWS_API_KEY)"],
        "feature_descriptions": {
            "news_sentiment_score": {
                "label": "Sentiment Score",
                "description": "Mean VADER compound score across recent headlines. +1 = maximally positive, −1 = maximally negative. Buy: ≥0.10. Sell: ≤−0.10.",
                "range": "−1 to +1",
            },
            "news_headline_count": {
                "label": "Headline Count",
                "description": "Number of headlines scored. Signals require ≥3 headlines; fewer = hold regardless of sentiment.",
                "range": "0 and up",
            },
        },
        "signal_logic": "BUY when price uptrend (close > fast SMA > slow SMA) AND sentiment ≥ 0.10. SELL when price < fast SMA AND sentiment ≤ −0.10.",
    },
    "Social": {
        "description": "Aggregates social signal strength from Google Trends interest (no API key) and Reddit post sentiment across r/stocks, r/investing, and r/wallstreetbets (requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET).",
        "data_sources": ["Google Trends (pytrends)", "Reddit r/stocks", "Reddit r/investing", "Reddit r/wallstreetbets"],
        "feature_descriptions": {
            "social_trend_score": {
                "label": "Trend Score",
                "description": "Google Trends 30-day interest index, normalised 0–1. 1.0 = peak search interest for this ticker. Buy threshold: ≥0.40.",
                "range": "0–1",
            },
            "social_mention_count": {
                "label": "Reddit Mentions",
                "description": "Number of recent Reddit posts mentioning this ticker across the tracked subreddits.",
                "range": "0 and up",
            },
            "social_reddit_sentiment": {
                "label": "Reddit Sentiment",
                "description": "Mean VADER compound score of Reddit post titles. +1 = fully positive. Contributes to buy/sell threshold alongside trend score.",
                "range": "−1 to +1",
            },
        },
        "signal_logic": "BUY when trend_score ≥ 0.40 AND mention_count > 0 AND reddit_sentiment > 0. SELL when trend_score < 0.40 AND reddit_sentiment < 0.",
    },
}


def _interpret_signal(strategy_id: str, features: dict) -> str:
    if strategy_id == "policy_regime":
        score = features.get("policy_risk_on_score")
        tilt = features.get("policy_defensive_tilt")
        if score is None:
            return "No feature data"
        env = "Risk-on (bullish)" if score >= 0.55 else ("Risk-off (bearish)" if score < 0.45 else "Neutral")
        tilt_note = f", defensive tilt {tilt:+.3f}" if tilt is not None else ""
        return f"{env} — score {score:.2f}{tilt_note}"
    if strategy_id == "news_sentiment":
        score = features.get("news_sentiment_score")
        count = features.get("news_headline_count")
        if score is None:
            return "No headlines"
        sentiment = "Positive" if score >= 0.10 else ("Negative" if score <= -0.10 else "Neutral")
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


def _load_providers() -> tuple[
    list[tuple[Any, Any]],   # [(provider, strategy_id), ...]
    list[str],               # display names
    list[str],               # source_label fallbacks
    list[str],               # strategy ids
]:
    """Lazily import and instantiate the three alt-strategy providers.

    Each provider is imported and instantiated independently so that a single
    missing dependency does not prevent the others from loading.
    """
    from trading.features.news_feature_provider import NewsFeatureProvider
    from trading.features.policy_feature_provider import PolicyFeatureProvider
    from trading.features.social_feature_provider import SocialFeatureProvider

    provider_classes = {
        "PolicyFeatureProvider": PolicyFeatureProvider,
        "NewsFeatureProvider": NewsFeatureProvider,
        "SocialFeatureProvider": SocialFeatureProvider,
    }

    pairs: list[tuple[Any, Any]] = []
    names: list[str] = []
    labels: list[str] = []
    strategy_ids: list[str] = []

    for display_name, source_label, class_name, strategy_id in _PROVIDER_SPECS:
        try:
            provider = provider_classes[class_name]()
            pairs.append((provider, strategy_id))
        except Exception as exc:
            _LOG.warning("features: failed to init %s: %s", class_name, exc)
            pairs.append((None, None))
        names.append(display_name)
        labels.append(source_label)
        strategy_ids.append(strategy_id)

    return pairs, names, labels, strategy_ids


@router.get("/api/features/status")
def api_feature_status() -> dict[str, list[dict[str, Any]]]:
    """Probe all three alt-strategy feature providers and return their status."""
    pairs, names, labels, _ = _load_providers()
    results: list[dict[str, Any]] = []

    for (provider, _strategy_id), name, label in zip(pairs, names, labels):
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

    return {"providers": results}


@router.post("/api/features/signals")
def api_feature_signals(body: FeatureSignalsRequest) -> dict[str, Any]:
    """Run all three alt-strategy signal functions for the requested ticker.

    Note: signals are computed using feature data only (no price history).
    When feature data is available the signal is a real model output; when
    unavailable the signal falls back to ``"hold"`` with ``available: false``.
    """
    from trading.backtesting.domain.strategy_signals import resolve_signal

    ticker = body.ticker.strip().upper()
    pairs, names, _labels, strategy_ids = _load_providers()
    signals: list[dict[str, Any]] = []

    # Signal functions require a price Series for momentum guards.
    # Passing an empty Series means the length check always fires, so the
    # signal relies entirely on the feature bundle.  We mark available=false
    # to make clear that no price-based confirmation was performed.
    empty_history = pd.Series([], dtype=float)

    for (provider, _strategy_id), strategy_id, name in zip(pairs, strategy_ids, names):
        meta = _PROVIDER_META.get(name, {})
        signal_logic = meta.get("signal_logic", "")

        if provider is None:
            signals.append({
                "strategy": strategy_id,
                "signal": "hold",
                "available": False,
                "features": {},
                "signal_logic": signal_logic,
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
                "interpretation": "",
            })
            continue

        try:
            signal = resolve_signal(strategy_id, empty_history, bundle.to_feature_row())
        except Exception as exc:
            _LOG.warning("features: signal fn failed for %s/%s: %s", strategy_id, ticker, exc)
            signal = "hold"

        # available=False: no price history was supplied, so the momentum
        # guards fired and any non-hold result is feature-only (degraded).
        signals.append({
            "strategy": strategy_id,
            "signal": signal,
            "available": False,
            "features": bundle.features,
            "reason": "no_price_history",
            "signal_logic": signal_logic,
            "interpretation": _interpret_signal(strategy_id, bundle.features),
        })

    return {"ticker": ticker, "signals": signals}
