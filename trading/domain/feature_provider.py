"""Domain contracts for external feature providers and signal keys."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# Policy-regime feature keys consumed by alternative strategy signals.
POLICY_RISK_ON_SCORE = "policy_risk_on_score"
POLICY_DEFENSIVE_TILT = "policy_defensive_tilt"

# Policy regime thresholds consumed by signal logic.
POLICY_RISK_ON_BUY_THRESHOLD = 0.55
POLICY_RISK_OFF_SELL_THRESHOLD = 0.45
POLICY_MAX_DEFENSIVE_TILT = 0.02

# News sentiment feature keys consumed by alternative strategy signals.
NEWS_SENTIMENT_SCORE = "news_sentiment_score"
NEWS_HEADLINE_COUNT = "news_headline_count"

# News sentiment thresholds consumed by signal logic.
NEWS_BUY_SENTIMENT_THRESHOLD = 0.10
NEWS_SELL_SENTIMENT_THRESHOLD = -0.10
NEWS_MIN_HEADLINES_REQUIRED = 3.0

# Social feature keys consumed by alternative strategy signals.
SOCIAL_TREND_SCORE = "social_trend_score"
SOCIAL_MENTION_COUNT = "social_mention_count"
SOCIAL_REDDIT_SENTIMENT = "social_reddit_sentiment"

# Social trend thresholds consumed by signal logic.
SOCIAL_TREND_BUY_THRESHOLD = 0.40
SOCIAL_TREND_EXIT_THRESHOLD = 0.20
SOCIAL_MIN_REDDIT_SENTIMENT = -0.05


@dataclass
class ExternalFeatureBundle:
    """Container for features returned by an :class:`ExternalFeatureProvider`."""

    features: dict[str, float] = field(default_factory=dict)
    available: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""

    def get(self, key: str, default: float | None = None) -> float | None:
        """Return the named feature value, or *default* if not present."""
        return self.features.get(key, default)

    def to_feature_row(self) -> pd.DataFrame | None:
        """Return a single-row DataFrame of features, or None if unavailable."""
        if not self.available:
            return None
        return pd.DataFrame([self.features])

    @classmethod
    def unavailable(cls, source: str = "") -> ExternalFeatureBundle:
        """Return a sentinel bundle indicating data is not available."""
        return cls(features={}, available=False, source=source)


@dataclass
class FeatureFetcherSet:
    """Groups the three feature-fetch callables needed for rotation."""

    fetch_policy: Callable[[str], ExternalFeatureBundle]
    fetch_news: Callable[[str], ExternalFeatureBundle] | None = None
    fetch_social: Callable[[str], ExternalFeatureBundle] | None = None


_DEFAULT_CACHE_TTL_SECONDS = 300


class ExternalFeatureProvider(ABC):
    """Abstract base class for external-data feature providers."""

    def __init__(self, *, cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, ExternalFeatureBundle] = {}

    def get_features(self, ticker: str) -> ExternalFeatureBundle:
        """Return features for *ticker*, using the cache when fresh."""
        cached = self._cache.get(ticker)
        if cached is not None and self._is_fresh(cached):
            return cached

        try:
            bundle = self._fetch(ticker)
        except Exception as exc:
            logger.warning("Feature fetch failed for %s (%s): %s", ticker, self.source_label, exc, exc_info=True)
            bundle = ExternalFeatureBundle.unavailable(source=self.source_label)

        self._cache[ticker] = bundle
        return bundle

    def invalidate(self, ticker: str | None = None) -> None:
        """Clear cached data for *ticker*, or all tickers if ``None``."""
        if ticker is None:
            self._cache.clear()
        else:
            self._cache.pop(ticker, None)

    @property
    @abstractmethod
    def source_label(self) -> str:
        """Short human-readable label for the data source."""

    @abstractmethod
    def _fetch(self, ticker: str) -> ExternalFeatureBundle:
        """Fetch fresh feature data for *ticker* from the external source."""

    def _is_fresh(self, bundle: ExternalFeatureBundle) -> bool:
        age = datetime.now(timezone.utc) - bundle.fetched_at
        return age < self._cache_ttl

    @property
    def _feature_names(self) -> tuple[str, ...]:
        """Optional advertised feature names for documentation and validation."""
        return ()
