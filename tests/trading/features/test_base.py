"""Tests for trading.features.base — ExternalFeatureBundle and ExternalFeatureProvider."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from trading.features.base import (
    ExternalFeatureBundle,
    ExternalFeatureProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubProvider(ExternalFeatureProvider):
    """Minimal concrete provider for testing base-class behaviour."""

    def __init__(self, *, raises: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.fetch_count = 0
        self._raises = raises

    @property
    def source_label(self) -> str:
        return "stub"

    def _fetch(self, ticker: str) -> ExternalFeatureBundle:
        self.fetch_count += 1
        if self._raises:
            raise RuntimeError("simulated external API failure")
        return ExternalFeatureBundle(
            features={"score": 0.75},
            available=True,
            source=self.source_label,
        )


# ---------------------------------------------------------------------------
# ExternalFeatureBundle tests
# ---------------------------------------------------------------------------


class TestExternalFeatureBundle:
    def test_available_bundle_get_returns_value(self):
        bundle = ExternalFeatureBundle(features={"x": 1.0}, available=True, source="test")
        assert bundle.get("x") == 1.0

    def test_get_missing_key_returns_default(self):
        bundle = ExternalFeatureBundle(features={}, available=True, source="test")
        assert bundle.get("missing") is None
        assert bundle.get("missing", 0.5) == 0.5

    def test_unavailable_sentinel_has_correct_flags(self):
        bundle = ExternalFeatureBundle.unavailable(source="test-src")
        assert bundle.available is False
        assert bundle.features == {}
        assert bundle.source == "test-src"

    def test_unavailable_default_source_is_empty_string(self):
        bundle = ExternalFeatureBundle.unavailable()
        assert bundle.source == ""

    def test_fetched_at_defaults_to_utc_now(self):
        before = datetime.now(timezone.utc)
        bundle = ExternalFeatureBundle(features={}, available=True, source="t")
        after = datetime.now(timezone.utc)
        assert before <= bundle.fetched_at <= after

    def test_default_available_is_false(self):
        bundle = ExternalFeatureBundle()
        assert bundle.available is False


# ---------------------------------------------------------------------------
# ExternalFeatureProvider — caching
# ---------------------------------------------------------------------------


class TestExternalFeatureProviderCaching:
    def test_fresh_result_is_cached(self):
        provider = _StubProvider(cache_ttl_seconds=60)
        b1 = provider.get_features("AAPL")
        b2 = provider.get_features("AAPL")
        assert b1 is b2
        assert provider.fetch_count == 1

    def test_stale_cache_triggers_refetch(self):
        provider = _StubProvider(cache_ttl_seconds=60)
        provider.get_features("AAPL")
        # Back-date the cached bundle to make it stale.
        cached = provider._cache["AAPL"]
        provider._cache["AAPL"] = ExternalFeatureBundle(
            features=cached.features,
            available=cached.available,
            fetched_at=datetime.now(timezone.utc) - timedelta(seconds=120),
            source=cached.source,
        )
        provider.get_features("AAPL")
        assert provider.fetch_count == 2

    def test_different_tickers_fetched_independently(self):
        provider = _StubProvider(cache_ttl_seconds=60)
        provider.get_features("AAPL")
        provider.get_features("MSFT")
        assert provider.fetch_count == 2

    def test_invalidate_single_ticker_clears_only_that_entry(self):
        provider = _StubProvider(cache_ttl_seconds=60)
        provider.get_features("AAPL")
        provider.get_features("MSFT")
        provider.invalidate("AAPL")
        assert "AAPL" not in provider._cache
        assert "MSFT" in provider._cache

    def test_invalidate_all_clears_entire_cache(self):
        provider = _StubProvider(cache_ttl_seconds=60)
        provider.get_features("AAPL")
        provider.get_features("MSFT")
        provider.invalidate()
        assert provider._cache == {}

    def test_invalidate_nonexistent_ticker_is_safe(self):
        provider = _StubProvider(cache_ttl_seconds=60)
        provider.invalidate("UNKNOWN")  # must not raise


# ---------------------------------------------------------------------------
# ExternalFeatureProvider — graceful degradation
# ---------------------------------------------------------------------------


class TestExternalFeatureProviderDegradation:
    def test_fetch_exception_returns_unavailable_bundle(self):
        provider = _StubProvider(raises=True)
        bundle = provider.get_features("AAPL")
        assert bundle.available is False
        assert bundle.source == "stub"

    def test_unavailable_bundle_still_cached(self):
        provider = _StubProvider(raises=True)
        provider.get_features("AAPL")
        provider.get_features("AAPL")
        # Only 1 fetch attempt because the unavailable result is cached.
        assert provider.fetch_count == 1

    def test_stale_unavailable_bundle_is_refetched(self):
        provider = _StubProvider(raises=True, cache_ttl_seconds=60)
        provider.get_features("AAPL")
        # Expire the cache manually.
        provider._cache["AAPL"] = ExternalFeatureBundle(
            available=False,
            fetched_at=datetime.now(timezone.utc) - timedelta(seconds=120),
            source="stub",
        )
        provider.get_features("AAPL")
        assert provider.fetch_count == 2

    def test_get_features_never_raises(self):
        """The public get_features method must never propagate exceptions."""

        class _ExplodingProvider(_StubProvider):
            def _fetch(self, ticker):
                raise ValueError("boom")

        provider = _ExplodingProvider()
        # Should not raise:
        bundle = provider.get_features("AAPL")
        assert bundle.available is False


# ---------------------------------------------------------------------------
# ExternalFeatureProvider — source_label on cached bundles
# ---------------------------------------------------------------------------


class TestSourceLabel:
    def test_source_label_propagated_to_bundle(self):
        provider = _StubProvider()
        bundle = provider.get_features("AAPL")
        assert bundle.source == "stub"

    def test_unavailable_bundle_carries_source_label(self):
        provider = _StubProvider(raises=True)
        bundle = provider.get_features("AAPL")
        assert bundle.source == "stub"
