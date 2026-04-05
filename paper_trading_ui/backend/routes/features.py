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


def _build_unavailable_entry(name: str, source_label: str) -> dict[str, Any]:
    return {
        "name": name,
        "source_label": source_label,
        "available": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "key_scores": {},
    }


def _load_providers_and_signals() -> tuple[
    list[tuple[Any, Any]],   # [(provider, signal_fn), ...]
    list[str],               # display names
    list[str],               # source_label fallbacks
    list[str],               # strategy ids
]:
    """Lazily import and instantiate the three alt-strategy providers and signal fns.

    Each provider is imported and instantiated independently so that a single
    missing dependency does not prevent the others from loading.
    """
    from trading.backtesting.domain.strategy_signals import (
        _news_sentiment_signal,
        _policy_regime_signal,
        _social_trend_rotation_signal,
    )
    from trading.features.news_feature_provider import NewsFeatureProvider
    from trading.features.policy_feature_provider import PolicyFeatureProvider
    from trading.features.social_feature_provider import SocialFeatureProvider

    provider_classes = {
        "PolicyFeatureProvider": PolicyFeatureProvider,
        "NewsFeatureProvider": NewsFeatureProvider,
        "SocialFeatureProvider": SocialFeatureProvider,
    }
    signal_fns = {
        "policy_regime": _policy_regime_signal,
        "news_sentiment": _news_sentiment_signal,
        "social_trend_rotation": _social_trend_rotation_signal,
    }

    pairs: list[tuple[Any, Any]] = []
    names: list[str] = []
    labels: list[str] = []
    strategy_ids: list[str] = []

    for display_name, source_label, class_name, strategy_id in _PROVIDER_SPECS:
        try:
            provider = provider_classes[class_name]()
            sig_fn = signal_fns[strategy_id]
            pairs.append((provider, sig_fn))
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
    pairs, names, labels, _ = _load_providers_and_signals()
    results: list[dict[str, Any]] = []

    for (provider, _sig_fn), name, label in zip(pairs, names, labels):
        if provider is None:
            results.append(_build_unavailable_entry(name, label))
            continue
        try:
            bundle = provider.get_features(_HEALTH_PROBE_TICKER)
            results.append({
                "name": name,
                "source_label": provider.source_label,
                "available": bundle.available,
                "fetched_at": bundle.fetched_at.isoformat(),
                "key_scores": bundle.features if bundle.available else {},
            })
        except Exception as exc:
            _LOG.warning("features: status probe failed for %s: %s", name, exc)
            results.append(_build_unavailable_entry(name, label))

    return {"providers": results}


@router.post("/api/features/signals")
def api_feature_signals(body: FeatureSignalsRequest) -> dict[str, Any]:
    """Run all three alt-strategy signal functions for the requested ticker."""
    ticker = body.ticker.strip().upper()
    pairs, _names, _labels, strategy_ids = _load_providers_and_signals()
    signals: list[dict[str, Any]] = []

    # Alt-strategy signal functions require a price Series; passing an empty
    # Series results in a "hold" from the length guard, which is the correct
    # degraded behaviour when no price history is supplied via this endpoint.
    empty_history = pd.Series([], dtype=float)

    for (provider, sig_fn), strategy_id in zip(pairs, strategy_ids):
        if provider is None or sig_fn is None:
            signals.append({
                "strategy": strategy_id,
                "signal": "hold",
                "available": False,
                "features": {},
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
            })
            continue

        if not bundle.available:
            signals.append({
                "strategy": strategy_id,
                "signal": "hold",
                "available": False,
                "features": {},
            })
            continue

        try:
            signal = sig_fn(empty_history, {}, bundle.to_feature_row())
        except Exception as exc:
            _LOG.warning("features: signal fn failed for %s/%s: %s", strategy_id, ticker, exc)
            signal = "hold"

        signals.append({
            "strategy": strategy_id,
            "signal": signal,
            "available": True,
            "features": bundle.features,
        })

    return {"ticker": ticker, "signals": signals}
