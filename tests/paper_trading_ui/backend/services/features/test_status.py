from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from paper_trading_ui.backend.services.features import status as features_status


@dataclass
class _FakeBundle:
    available: bool
    features: dict[str, Any]
    fetched_at: datetime


class _FakeProvider:
    def __init__(self, *, bundle: _FakeBundle | None = None, source_label: str = "fake", error: Exception | None = None):
        self._bundle = bundle
        self.source_label = source_label
        self._error = error

    def get_features(self, _ticker: str) -> _FakeBundle:
        if self._error is not None:
            raise self._error
        assert self._bundle is not None
        return self._bundle


def test_get_provider_status_returns_unavailable_entry_when_provider_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        features_status,
        "load_providers",
        lambda: [(None, "Policy", "etf-proxies", "policy_regime", "PolicyFeatureProvider")],
    )

    providers = features_status.get_provider_status()

    assert len(providers) == 1
    assert providers[0]["name"] == "Policy"
    assert providers[0]["available"] is False
    assert providers[0]["key_scores"] == {}
    assert providers[0]["description"] is not None


def test_get_provider_status_serializes_available_bundle(monkeypatch) -> None:
    fetched_at = datetime(2026, 4, 24, 12, 34, 56, tzinfo=timezone.utc)
    provider = _FakeProvider(
        bundle=_FakeBundle(
            available=True,
            features={"news_sentiment_score": 0.42, "news_headline_count": 6},
            fetched_at=fetched_at,
        ),
        source_label="rss+vader",
    )
    monkeypatch.setattr(
        features_status,
        "load_providers",
        lambda: [(provider, "News", "rss+vader", "news_sentiment", "NewsFeatureProvider")],
    )

    providers = features_status.get_provider_status()

    assert len(providers) == 1
    assert providers[0]["name"] == "News"
    assert providers[0]["available"] is True
    assert providers[0]["source_label"] == "rss+vader"
    assert providers[0]["fetched_at"] == fetched_at.isoformat()
    assert providers[0]["key_scores"] == {"news_sentiment_score": 0.42, "news_headline_count": 6}
    assert providers[0]["feature_descriptions"] is not None
    assert providers[0]["signal_logic"] is not None


def test_get_provider_status_handles_provider_probe_error(monkeypatch) -> None:
    provider = _FakeProvider(error=RuntimeError("boom"))
    monkeypatch.setattr(
        features_status,
        "load_providers",
        lambda: [(provider, "Social", "reddit+gtrends", "social_trend_rotation", "SocialFeatureProvider")],
    )

    providers = features_status.get_provider_status()

    assert len(providers) == 1
    assert providers[0]["name"] == "Social"
    assert providers[0]["available"] is False
    assert providers[0]["key_scores"] == {}
