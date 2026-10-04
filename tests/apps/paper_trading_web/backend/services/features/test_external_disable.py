from __future__ import annotations

from paper_trading_web.backend.services.features.shared import load_providers
from paper_trading_web.backend.services.features.status import get_provider_status


def test_external_feature_disable_returns_unavailable_without_providers(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_EXTERNAL_FEATURES_DISABLED", "1")

    assert all(provider is None for provider, *_metadata in load_providers())
    assert all(entry["available"] is False for entry in get_provider_status())
