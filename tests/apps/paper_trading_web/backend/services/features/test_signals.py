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


def test_get_signals_uses_resolve_signal_for_available_bundle(monkeypatch) -> None:
    provider = _FakeProvider(bundle=_FakeBundle(available=True, features={"policy_risk_on_score": 0.65}))
    monkeypatch.setattr(
        features_signals,
        "load_providers",
        lambda: [(provider, "Policy", "etf-proxies", "policy_regime", "PolicyFeatureProvider")],
    )

    calls: list[tuple[str, dict[str, Any], int]] = []

    def _fake_resolve_signal(strategy_id: str, price_history, feature_row: dict[str, Any]) -> str:
        calls.append((strategy_id, feature_row, len(price_history)))
        return "buy"

    monkeypatch.setattr(features_signals, "resolve_signal", _fake_resolve_signal)
    monkeypatch.setattr(features_signals, "interpret_signal", lambda *_args, **_kwargs: "Risk-on (bullish)")

    signals = features_signals.get_signals("SPY")

    assert calls == [("policy_regime", {"policy_risk_on_score": 0.65}, 0)]
    assert signals[0]["signal"] == "buy"
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


def test_get_signals_returns_hold_when_signal_resolution_raises(monkeypatch) -> None:
    provider = _FakeProvider(bundle=_FakeBundle(available=True, features={"social_trend_score": 0.72}))
    monkeypatch.setattr(
        features_signals,
        "load_providers",
        lambda: [(provider, "Social", "reddit+gtrends", "social_trend_rotation", "SocialFeatureProvider")],
    )
    monkeypatch.setattr(
        features_signals, "resolve_signal", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom"))
    )
    monkeypatch.setattr(features_signals, "interpret_signal", lambda *_args, **_kwargs: "Trend interest 72%")

    signals = features_signals.get_signals("TSLA")

    assert len(signals) == 1
    assert signals[0]["strategy"] == "social_trend_rotation"
    assert signals[0]["signal"] == "hold"
    assert signals[0]["available"] is False
    assert signals[0]["reason"] == "no_price_history"
    assert signals[0]["features"] == {"social_trend_score": 0.72}
    assert signals[0]["interpretation"] == "Trend interest 72%"


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
