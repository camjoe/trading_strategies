"""Policy regime feature provider — ETF market proxies.

Uses publicly available ETF price data (via yfinance) to derive a
market-based policy/macro regime score.  No API key is required.

Proxy ETFs used:
    TLT  — 20+ yr US Treasuries (risk-off / flight-to-safety indicator)
    GLD  — Gold (flight-to-safety / inflation hedge)
    XLU  — Utilities sector (defensive equity rotation signal)
    UUP  — USD Index ETF (USD strength = risk-off for global markets)
    SPY  — S&P 500 (equity risk benchmark)

Features emitted (all float, available in a successful bundle):
    policy_risk_on_score   — 0–1 composite; higher = more risk-on environment.
                             Derived from SPY trailing return minus mean
                             defensive ETF return, sigmoid-normalised.
    policy_defensive_tilt  — Signed float; positive = defensives outperforming
                             equities over the lookback window.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import yfinance as yf

from trading.features.base import ExternalFeatureBundle, ExternalFeatureProvider

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature name constants — import these in signal functions and
# StrategySpec.required_features to avoid fragile string literals.
# ---------------------------------------------------------------------------

POLICY_RISK_ON_SCORE = "policy_risk_on_score"
POLICY_DEFENSIVE_TILT = "policy_defensive_tilt"

# ---------------------------------------------------------------------------
# ETF universe
# ---------------------------------------------------------------------------

_DEFENSIVE_ETFS: tuple[str, ...] = ("TLT", "GLD", "XLU", "UUP")
_EQUITY_BENCHMARK: str = "SPY"
_ALL_ETFS: tuple[str, ...] = _DEFENSIVE_ETFS + (_EQUITY_BENCHMARK,)

# ---------------------------------------------------------------------------
# Lookback / data-quality thresholds
# ---------------------------------------------------------------------------

# Calendar days fetched from yfinance (~21 trading days within this window).
POLICY_LOOKBACK_CALENDAR_DAYS = 45

# Minimum trading-day price observations required before trusting the signal.
POLICY_MIN_OBSERVATIONS = 15

# Sigmoid scale factor: maps ±10 % equity/defensive spread to ≈ 0.73 / 0.27.
_SIGMOID_SCALE = 10.0


class PolicyFeatureProvider(ExternalFeatureProvider):
    """Derive policy/macro regime features from ETF price relatives.

    The provider is ticker-agnostic: the same market-wide regime features are
    returned regardless of which ticker is queried.  The ``ticker`` parameter
    is accepted to satisfy the
    :class:`~trading.features.base.ExternalFeatureProvider` interface.

    Example usage::

        provider = PolicyFeatureProvider()
        bundle = provider.get_features("AAPL")
        if not bundle.available:
            return "hold"
        risk_on = bundle.get(POLICY_RISK_ON_SCORE, 0.5)
    """

    # All tickers share one cache entry since this is a market-wide signal.
    _REGIME_CACHE_KEY = "__regime__"

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

        defensive_rets = [returns[e] for e in _DEFENSIVE_ETFS if e in returns]
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
        """Download trailing returns for all proxy ETFs.

        Returns a ``{ticker: trailing_return_fraction}`` dict, or ``None``
        if the download fails or there is insufficient data.
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=POLICY_LOOKBACK_CALENDAR_DAYS)

        try:
            raw = yf.download(
                list(_ALL_ETFS),
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
        except Exception as exc:
            _LOG.warning("PolicyFeatureProvider: yfinance download failed: %s", exc)
            return None

        if raw.empty:
            return None

        # yfinance returns a MultiIndex when multiple tickers are requested.
        close = raw.get("Close", raw.xs("Close", level=0, axis=1) if isinstance(raw.columns, object) else None)
        if close is None or close.empty or len(close) < POLICY_MIN_OBSERVATIONS:
            return None

        results: dict[str, float] = {}
        for etf in _ALL_ETFS:
            if etf not in close.columns:
                _LOG.debug("PolicyFeatureProvider: %s missing from download", etf)
                continue
            series = close[etf].dropna()
            if len(series) < 2:
                continue
            first, last = float(series.iloc[0]), float(series.iloc[-1])
            if first == 0.0:
                continue
            results[etf] = (last - first) / first

        return results or None
