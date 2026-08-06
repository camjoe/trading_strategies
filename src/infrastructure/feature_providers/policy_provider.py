"""Policy regime feature provider — ETF market proxies."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from infrastructure.market_data.factory import build_provider
from trading.domain.feature_provider import (
    POLICY_DEFENSIVE_TILT,
    POLICY_MAX_DEFENSIVE_TILT,
    POLICY_RISK_OFF_SELL_THRESHOLD,
    POLICY_RISK_ON_BUY_THRESHOLD,
    POLICY_RISK_ON_SCORE,
    ExternalFeatureBundle,
    ExternalFeatureProvider,
)
from trading.services.market_data import MarketDataProvider

_LOG = logging.getLogger(__name__)

_DEFENSIVE_ETFS: tuple[str, ...] = ("TLT", "GLD", "XLU", "UUP")
_EQUITY_BENCHMARK: str = "SPY"
_ALL_ETFS: tuple[str, ...] = _DEFENSIVE_ETFS + (_EQUITY_BENCHMARK,)

# Calendar days fetched from yfinance (~21 trading days within this window).
POLICY_LOOKBACK_CALENDAR_DAYS = 45

# Minimum trading-day price observations required before trusting the signal.
POLICY_MIN_OBSERVATIONS = 15

# Sigmoid scale factor: maps ±10 % equity/defensive spread to ≈ 0.73 / 0.27.
_SIGMOID_SCALE = 10.0


class PolicyFeatureProvider(ExternalFeatureProvider):
    """Derive policy/macro regime features from ETF price relatives.

    The provider is ticker-agnostic: the same market-wide regime features are
    returned regardless of which ticker is queried. The ``ticker`` parameter
    is accepted to satisfy the
    :class:`~trading.domain.feature_provider.ExternalFeatureProvider` interface.
    """

    _REGIME_CACHE_KEY = "__regime__"

    def __init__(self, *, market_data_provider: MarketDataProvider | None = None) -> None:
        super().__init__()
        self._market_data = market_data_provider or build_provider()

    @property
    def source_label(self) -> str:
        return "etf-proxies"

    @property
    def _feature_names(self) -> tuple[str, ...]:
        return (POLICY_RISK_ON_SCORE, POLICY_DEFENSIVE_TILT)

    def get_features(self, ticker: str) -> ExternalFeatureBundle:
        """Return policy regime features (identical for all tickers)."""
        return super().get_features(self._REGIME_CACHE_KEY)

    def _fetch(self, _ticker: str) -> ExternalFeatureBundle:
        returns = self._fetch_etf_returns()
        if returns is None:
            return ExternalFeatureBundle.unavailable(source=self.source_label)

        spy_ret = returns.get(_EQUITY_BENCHMARK)
        if spy_ret is None:
            return ExternalFeatureBundle.unavailable(source=self.source_label)

        defensive_rets = [returns[etf] for etf in _DEFENSIVE_ETFS if etf in returns]
        if not defensive_rets:
            return ExternalFeatureBundle.unavailable(source=self.source_label)

        mean_defensive = sum(defensive_rets) / len(defensive_rets)
        raw_spread = float(spy_ret) - mean_defensive
        risk_on_score = 1.0 / (1.0 + math.exp(-_SIGMOID_SCALE * raw_spread))

        return ExternalFeatureBundle(
            features={
                POLICY_RISK_ON_SCORE: round(risk_on_score, 6),
                POLICY_DEFENSIVE_TILT: round(mean_defensive - float(spy_ret), 6),
            },
            available=True,
            source=self.source_label,
        )

    def _fetch_etf_returns(self) -> dict[str, float] | None:
        """Return each proxy ETF's trailing return, or None if the basket is incomplete."""
        # Ends yesterday: today's bar is still forming.
        today = datetime.now(timezone.utc).date()
        end = today - timedelta(days=1)
        start = today - timedelta(days=POLICY_LOOKBACK_CALENDAR_DAYS)

        try:
            close = self._market_data.fetch_close_history(list(_ALL_ETFS), start, end)
        except Exception as exc:
            _LOG.warning("PolicyFeatureProvider: ETF close history unavailable: %s", exc)
            return None

        if len(close) < POLICY_MIN_OBSERVATIONS:
            return None

        results: dict[str, float] = {}
        for etf in _ALL_ETFS:
            series = close[etf].dropna()
            if len(series) < 2:
                return None
            first, last = float(series.iloc[0]), float(series.iloc[-1])
            if first == 0.0:
                return None
            results[etf] = (last - first) / first

        return results


__all__ = [
    "POLICY_DEFENSIVE_TILT",
    "POLICY_MAX_DEFENSIVE_TILT",
    "POLICY_RISK_OFF_SELL_THRESHOLD",
    "POLICY_RISK_ON_BUY_THRESHOLD",
    "POLICY_RISK_ON_SCORE",
    "PolicyFeatureProvider",
]
