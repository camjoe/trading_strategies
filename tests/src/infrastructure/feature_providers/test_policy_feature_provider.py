"""Tests for PolicyFeatureProvider and the policy_regime signal function."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pandas as pd

from infrastructure.feature_providers.policy_provider import (
    _ALL_ETFS,
    _EQUITY_BENCHMARK,
    POLICY_DEFENSIVE_TILT,
    POLICY_LOOKBACK_CALENDAR_DAYS,
    POLICY_MIN_OBSERVATIONS,
    POLICY_RISK_ON_SCORE,
    PolicyFeatureProvider,
)
from trading.services.market_data import MarketDataProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubMarketData(MarketDataProvider):
    """Serves one canned close-history result, or raises the one it was given."""

    def __init__(self, close: pd.DataFrame | Exception) -> None:
        self._close = close
        self.calls: list[tuple[list[str], date, date]] = []

    def fetch_close_history(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        self.calls.append((list(tickers), start_date, end_date))
        if isinstance(self._close, Exception):
            raise self._close
        return self._close

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        raise NotImplementedError

    def fetch_bar_history(self, tickers: list[str], start_date: date, end_date: date) -> dict[str, pd.DataFrame]:
        raise NotImplementedError


def _make_close_df(tickers: list[str], rows: int = 20, base: float = 100.0) -> pd.DataFrame:
    """Build a fake multi-ticker Close DataFrame of incrementing prices."""
    data = {t: [base + i * 0.5 for i in range(rows)] for t in tickers}
    return pd.DataFrame(data)


def _provider_reading(close: pd.DataFrame | Exception) -> tuple[PolicyFeatureProvider, _StubMarketData]:
    stub = _StubMarketData(close)
    return PolicyFeatureProvider(market_data_provider=stub), stub


def _make_feature_history(risk_on: float, def_tilt: float) -> pd.DataFrame:
    return pd.DataFrame({POLICY_RISK_ON_SCORE: [risk_on], POLICY_DEFENSIVE_TILT: [def_tilt]})


def _make_history(n: int = 60, start: float = 100.0, slope: float = 0.5) -> pd.Series:
    return pd.Series([start + i * slope for i in range(n)])


# ---------------------------------------------------------------------------
# PolicyFeatureProvider — _fetch_etf_returns
# ---------------------------------------------------------------------------


class TestPolicyFeatureProviderFetchReturns:
    def test_returns_dict_with_all_etfs_on_success(self):
        close = _make_close_df(list(_ALL_ETFS), rows=POLICY_MIN_OBSERVATIONS + 2)
        provider, _ = _provider_reading(close)

        result = provider._fetch_etf_returns()

        assert result is not None
        assert set(result) == set(_ALL_ETFS)

    def test_requests_the_whole_basket_in_one_read(self):
        close = _make_close_df(list(_ALL_ETFS), rows=POLICY_MIN_OBSERVATIONS + 2)
        provider, stub = _provider_reading(close)

        provider._fetch_etf_returns()

        assert len(stub.calls) == 1
        assert stub.calls[0][0] == list(_ALL_ETFS)

    def test_window_ends_before_today(self):
        """Today's bar is still forming; including it moves the regime with the tape."""
        close = _make_close_df(list(_ALL_ETFS), rows=POLICY_MIN_OBSERVATIONS + 2)
        provider, stub = _provider_reading(close)

        provider._fetch_etf_returns()

        _tickers, start_date, end_date = stub.calls[0]
        today = datetime.now(timezone.utc).date()
        assert end_date < today
        assert (today - start_date).days == POLICY_LOOKBACK_CALENDAR_DAYS

    def test_returns_none_when_the_read_fails(self):
        provider, _ = _provider_reading(RuntimeError("network error"))

        assert provider._fetch_etf_returns() is None

    def test_returns_none_when_an_etf_is_missing_from_the_basket(self):
        """mean_defensive is a basket average, so a short basket is no signal, not a rebased one."""
        provider, _ = _provider_reading(ValueError("Missing close history for tickers: GLD"))

        assert provider._fetch_etf_returns() is None

    def test_returns_none_when_history_is_too_short(self):
        close = _make_close_df(list(_ALL_ETFS), rows=POLICY_MIN_OBSERVATIONS - 1)
        provider, _ = _provider_reading(close)

        assert provider._fetch_etf_returns() is None

    def test_returns_none_when_an_etf_series_is_too_short(self):
        close = _make_close_df(list(_ALL_ETFS), rows=POLICY_MIN_OBSERVATIONS + 2)
        close["GLD"] = float("nan")
        provider, _ = _provider_reading(close)

        assert provider._fetch_etf_returns() is None

    def test_returns_none_when_an_etf_opens_at_zero(self):
        close = _make_close_df(list(_ALL_ETFS), rows=POLICY_MIN_OBSERVATIONS + 2)
        close["GLD"] = [0.0] + [100.0] * (POLICY_MIN_OBSERVATIONS + 1)
        provider, _ = _provider_reading(close)

        assert provider._fetch_etf_returns() is None

    def test_feature_names_contains_expected_keys(self):
        provider, _ = _provider_reading(_make_close_df(list(_ALL_ETFS)))
        assert POLICY_RISK_ON_SCORE in provider._feature_names
        assert POLICY_DEFENSIVE_TILT in provider._feature_names


# ---------------------------------------------------------------------------
# PolicyFeatureProvider — _fetch (bundle computation)
# ---------------------------------------------------------------------------


class TestPolicyFeatureProviderFetch:
    def _provider_with_returns(self, spy_ret: float, defensive_rets: dict[str, float]):
        """Build a provider whose _fetch_etf_returns is patched to return fixed data."""
        provider, _ = _provider_reading(_make_close_df(list(_ALL_ETFS)))
        all_returns = {_EQUITY_BENCHMARK: spy_ret, **defensive_rets}
        provider._fetch_etf_returns = MagicMock(return_value=all_returns)
        return provider

    def test_available_bundle_when_all_data_present(self):
        provider = self._provider_with_returns(
            spy_ret=0.05,
            defensive_rets={"TLT": 0.02, "GLD": 0.01, "XLU": 0.01, "UUP": 0.00},
        )
        bundle = provider._fetch("ANY")
        assert bundle.available is True
        assert POLICY_RISK_ON_SCORE in bundle.features
        assert POLICY_DEFENSIVE_TILT in bundle.features

    def test_risk_on_score_between_0_and_1(self):
        provider = self._provider_with_returns(
            spy_ret=0.05,
            defensive_rets={"TLT": 0.01, "GLD": 0.01, "XLU": 0.01, "UUP": 0.01},
        )
        bundle = provider._fetch("ANY")
        score = bundle.get(POLICY_RISK_ON_SCORE)
        assert score is not None
        assert 0.0 < score < 1.0

    def test_high_spy_return_yields_high_risk_on_score(self):
        provider = self._provider_with_returns(
            spy_ret=0.15,
            defensive_rets={"TLT": -0.05, "GLD": -0.03, "XLU": -0.02, "UUP": -0.01},
        )
        bundle = provider._fetch("ANY")
        assert bundle.get(POLICY_RISK_ON_SCORE, 0.0) > 0.7

    def test_high_defensive_return_yields_low_risk_on_score(self):
        provider = self._provider_with_returns(
            spy_ret=-0.10,
            defensive_rets={"TLT": 0.08, "GLD": 0.06, "XLU": 0.05, "UUP": 0.04},
        )
        bundle = provider._fetch("ANY")
        assert bundle.get(POLICY_RISK_ON_SCORE, 1.0) < 0.3

    def test_defensive_tilt_positive_when_defensives_outperform(self):
        provider = self._provider_with_returns(
            spy_ret=0.00,
            defensive_rets={"TLT": 0.05, "GLD": 0.05, "XLU": 0.05, "UUP": 0.05},
        )
        bundle = provider._fetch("ANY")
        assert bundle.get(POLICY_DEFENSIVE_TILT, -1.0) > 0.0

    def test_unavailable_when_spy_missing(self):
        provider, _ = _provider_reading(_make_close_df(list(_ALL_ETFS)))
        provider._fetch_etf_returns = MagicMock(
            return_value={"TLT": 0.02, "GLD": 0.01, "XLU": 0.01, "UUP": 0.00}
            # SPY intentionally absent
        )
        bundle = provider._fetch("ANY")
        assert bundle.available is False

    def test_unavailable_when_all_defensives_missing(self):
        provider, _ = _provider_reading(_make_close_df(list(_ALL_ETFS)))
        provider._fetch_etf_returns = MagicMock(
            return_value={_EQUITY_BENCHMARK: 0.05}
            # no defensive ETFs
        )
        bundle = provider._fetch("ANY")
        assert bundle.available is False

    def test_unavailable_when_returns_none(self):
        provider, _ = _provider_reading(_make_close_df(list(_ALL_ETFS)))
        provider._fetch_etf_returns = MagicMock(return_value=None)
        bundle = provider._fetch("ANY")
        assert bundle.available is False

    def test_source_label_on_available_bundle(self):
        provider = self._provider_with_returns(
            spy_ret=0.03,
            defensive_rets={"TLT": 0.01, "GLD": 0.01, "XLU": 0.01, "UUP": 0.01},
        )
        bundle = provider._fetch("ANY")
        assert bundle.source == "etf-proxies"


# ---------------------------------------------------------------------------
# PolicyFeatureProvider — cache sharing
# ---------------------------------------------------------------------------


class TestPolicyFeatureProviderCache:
    def test_different_tickers_share_same_cache_entry(self):
        provider, _ = _provider_reading(_make_close_df(list(_ALL_ETFS)))
        provider._fetch_etf_returns = MagicMock(
            return_value={
                _EQUITY_BENCHMARK: 0.03,
                "TLT": 0.01,
                "GLD": 0.01,
                "XLU": 0.01,
                "UUP": 0.01,
            }
        )
        b1 = provider.get_features("AAPL")
        b2 = provider.get_features("MSFT")
        assert b1 is b2
        assert provider._fetch_etf_returns.call_count == 1
