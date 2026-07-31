from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from paper_trading_web.backend.services.features import signals as features_signals


@dataclass
class _FakeBundle:
    available: bool
    features: dict[str, Any]
    fetched_at: datetime = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)

    def to_feature_row(self) -> dict[str, Any]:
        return dict(self.features)


class _FakeProvider:
    def __init__(self, *, bundle: _FakeBundle | None = None, error: Exception | None = None):
        self._bundle = bundle
        self._error = error

    def get_features(self, _ticker: str) -> _FakeBundle:
        if self._error is not None:
            raise self._error
        assert self._bundle is not None
        return self._bundle


def test_get_signals_returns_hold_for_missing_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        features_signals,
        "load_providers",
        lambda: [(None, "Policy", "etf-proxies", "policy_regime", "PolicyFeatureProvider")],
    )

    signals = features_signals.get_signals("SPY")

    assert len(signals) == 1
    assert signals[0]["strategy"] == "policy_regime"
    assert signals[0]["signal"] == "hold"
    assert signals[0]["available"] is False
    assert signals[0]["features"] == {}
    assert signals[0]["interpretation"] == ""


def test_get_signals_reports_features_without_a_signal(monkeypatch) -> None:
    """An available bundle yields its features and a hold.

    Nothing consumes these features since the feature-gated primitives were
    retired, so the panel reports what the provider sees rather than inventing a
    signal from a strategy that no longer exists.
    """
    provider = _FakeProvider(bundle=_FakeBundle(available=True, features={"policy_risk_on_score": 0.65}))
    monkeypatch.setattr(
        features_signals,
        "load_providers",
        lambda: [(provider, "Policy", "etf-proxies", "policy_regime", "PolicyFeatureProvider")],
    )
    monkeypatch.setattr(features_signals, "interpret_signal", lambda *_args, **_kwargs: "Risk-on (bullish)")

    signals = features_signals.get_signals("SPY")

    assert signals[0]["signal"] == "hold"
    assert signals[0]["available"] is False
    assert signals[0]["reason"] == "no_price_history"
    assert signals[0]["features"] == {"policy_risk_on_score": 0.65}
    assert signals[0]["interpretation"] == "Risk-on (bullish)"


def test_get_signals_returns_hold_when_provider_errors(monkeypatch) -> None:
    provider = _FakeProvider(error=RuntimeError("provider boom"))
    monkeypatch.setattr(
        features_signals,
        "load_providers",
        lambda: [(provider, "News", "rss+vader", "news_sentiment", "NewsFeatureProvider")],
    )

    signals = features_signals.get_signals("AAPL")

    assert len(signals) == 1
    assert signals[0]["strategy"] == "news_sentiment"
    assert signals[0]["signal"] == "hold"
    assert signals[0]["available"] is False
    assert signals[0]["features"] == {}
    assert signals[0]["interpretation"] == ""


def test_get_signals_returns_hold_when_bundle_unavailable(monkeypatch) -> None:
    provider = _FakeProvider(bundle=_FakeBundle(available=False, features={"ignored": 1}))
    monkeypatch.setattr(
        features_signals,
        "load_providers",
        lambda: [(provider, "News", "rss+vader", "news_sentiment", "NewsFeatureProvider")],
    )

    signals = features_signals.get_signals("AAPL")

    assert len(signals) == 1
    assert signals[0]["strategy"] == "news_sentiment"
    assert signals[0]["signal"] == "hold"
    assert signals[0]["available"] is False
    assert signals[0]["features"] == {}
    assert signals[0]["interpretation"] == ""
