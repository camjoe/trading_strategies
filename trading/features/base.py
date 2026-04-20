"""Base classes for external-data feature providers.

All ``strategy_style = "alternative"`` strategies depend on an
:class:`ExternalFeatureProvider` implementation to supply non-price
feature data.  This module defines the shared contract.

Design rules (enforced by BOT_ARCHITECTURE_CONVENTIONS.md):

1. All external network calls belong in a concrete subclass of
   :class:`ExternalFeatureProvider`.  Signal functions must never
   import or call external APIs directly.
2. Providers must degrade gracefully: when external data is unavailable
   or stale, :meth:`ExternalFeatureProvider.get_features` returns an
   :class:`ExternalFeatureBundle` whose :attr:`~ExternalFeatureBundle.available`
   flag is ``False``.  Signal functions treat ``available=False`` as a
   ``"hold"`` signal.
3. API keys go in environment variables only — never in source code.
   Use :func:`os.getenv` — never hard-code API keys.
4. Providers should cache results with a configurable TTL to avoid
   redundant API calls across multiple tickers in the same trading loop.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd



# ---------------------------------------------------------------------------
# Feature bundle
# ---------------------------------------------------------------------------


@dataclass
class ExternalFeatureBundle:
    """Container for features returned by an :class:`ExternalFeatureProvider`.

    Attributes:
        features:   Mapping of feature-name → numeric value (float).
                    Feature names must match the ``required_features`` tuple
                    declared on the consuming :class:`~trading.backtesting.domain.strategy_signals.StrategySpec`.
        available:  ``True`` when the provider successfully fetched fresh data.
                    ``False`` signals that the data is absent or stale; consuming
                    signal functions must return ``"hold"`` in this case.
        fetched_at: UTC timestamp of when the data was retrieved.
        source:     Human-readable label identifying the data origin
                    (e.g. ``"reddit+gtrends"``).  Used in log messages only.
    """

    features: dict[str, float] = field(default_factory=dict)
    available: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""

    def get(self, key: str, default: float | None = None) -> float | None:
        """Return the named feature value, or *default* if not present."""
        return self.features.get(key, default)

    def to_feature_row(self) -> pd.DataFrame | None:
        """Return a single-row DataFrame of features, or None if unavailable.

        Converts this bundle into the ``feature_history`` format expected by
        signal functions in ``trading.backtesting.domain.strategy_signals``.
        Returns ``None`` when :attr:`available` is ``False`` so that signal
        functions can treat it as a missing/stale data guard.
        """
        if not self.available:
            return None
        return pd.DataFrame([self.features])

    @classmethod
    def unavailable(cls, source: str = "") -> "ExternalFeatureBundle":
        """Return a sentinel bundle indicating data is not available."""
        return cls(features={}, available=False, source=source)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

# Default TTL for cached feature bundles.  Providers may override this.
_DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes


class ExternalFeatureProvider(ABC):
    """Abstract base class for external-data feature providers.

    Concrete subclasses (``PolicyFeatureProvider``, ``NewsFeatureProvider``,
    ``SocialFeatureProvider``) implement :meth:`_fetch` to call the relevant
    external service and return an :class:`ExternalFeatureBundle`.

    The base class handles:
    - Per-ticker result caching with a configurable TTL.
    - Graceful degradation: exceptions from :meth:`_fetch` are caught and
      an unavailable bundle is returned.
    - Logging-friendly ``source`` labels on every bundle.

    Usage::

        provider = ConcreteProvider(cache_ttl_seconds=60)
        bundle = provider.get_features("AAPL")
        if not bundle.available:
            return "hold"
        score = bundle.get("my_feature", 0.0)
    """

    def __init__(self, *, cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, ExternalFeatureBundle] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_features(self, ticker: str) -> ExternalFeatureBundle:
        """Return features for *ticker*, using the cache when fresh.

        Never raises — returns an unavailable bundle on any error so that
        calling signal functions can safely fall back to ``"hold"``.
        """
        cached = self._cache.get(ticker)
        if cached is not None and self._is_fresh(cached):
            return cached

        try:
            bundle = self._fetch(ticker)
        except Exception:
            bundle = ExternalFeatureBundle.unavailable(source=self.source_label)

        self._cache[ticker] = bundle
        return bundle

    def invalidate(self, ticker: str | None = None) -> None:
        """Clear cached data for *ticker*, or all tickers if ``None``."""
        if ticker is None:
            self._cache.clear()
        else:
            self._cache.pop(ticker, None)

    # ------------------------------------------------------------------
    # Abstract interface — implement in subclasses
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def source_label(self) -> str:
        """Short human-readable label for the data source (e.g. ``"reddit+gtrends"``)."""

    @abstractmethod
    def _fetch(self, ticker: str) -> ExternalFeatureBundle:
        """Fetch fresh feature data for *ticker* from the external source.

        Must return an :class:`ExternalFeatureBundle` with ``available=True``
        on success.  May raise any exception on failure — the base class
        catches it and returns an unavailable bundle.
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_fresh(self, bundle: ExternalFeatureBundle) -> bool:
        age = datetime.now(timezone.utc) - bundle.fetched_at
        return age < self._cache_ttl

    @property
    def _feature_names(self) -> tuple[str, ...]:
        """Optional: return feature names this provider supplies.

        Used for documentation and validation only — not enforced at runtime.
        Override in subclasses to advertise what keys appear in the bundle.
        """
        return ()
