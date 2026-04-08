"""Tests for PolicyFeatureProvider and the policy_regime signal function."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading.features.base import ExternalFeatureBundle
from trading.features.policy_feature_provider import (
    POLICY_DEFENSIVE_TILT,
    POLICY_RISK_ON_SCORE,
    PolicyFeatureProvider,
    _DEFENSIVE_ETFS,
    _EQUITY_BENCHMARK,
    POLICY_MIN_OBSERVATIONS,
)
from trading.backtesting.domain.strategy_signals import (
    STRATEGY_REGISTRY,
    resolve_strategy,
    _policy_regime_signal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close_df(tickers: list[str], rows: int = 20, base: float = 100.0) -> pd.DataFrame:
    """Build a fake multi-ticker Close DataFrame of incrementing prices."""
    import numpy as np
    data = {t: [base + i * 0.5 for i in range(rows)] for t in tickers}
    return pd.DataFrame(data)


def _make_raw_download(tickers: list[str], rows: int = 20) -> pd.DataFrame:
    """Simulate yfinance multi-ticker download result (MultiIndex columns)."""
    close_df = _make_close_df(tickers, rows)
    close_df.columns = pd.MultiIndex.from_product([["Close"], close_df.columns])
    return close_df


def _make_feature_history(risk_on: float, def_tilt: float) -> pd.DataFrame:
    return pd.DataFrame(
        {POLICY_RISK_ON_SCORE: [risk_on], POLICY_DEFENSIVE_TILT: [def_tilt]}
    )


def _make_history(n: int = 60, start: float = 100.0, slope: float = 0.5) -> pd.Series:
    return pd.Series([start + i * slope for i in range(n)])


# ---------------------------------------------------------------------------
# PolicyFeatureProvider — _fetch_etf_returns
# ---------------------------------------------------------------------------


class TestPolicyFeatureProviderFetchReturns:
    def test_returns_dict_with_all_etfs_on_success(self):
        all_tickers = list(_DEFENSIVE_ETFS) + [_EQUITY_BENCHMARK]
        raw = _make_raw_download(all_tickers, rows=POLICY_MIN_OBSERVATIONS + 2)

        provider = PolicyFeatureProvider()
        with patch("trading.features.policy_feature_provider.yf.download", return_value=raw):
            result = provider._fetch_etf_returns()

        assert result is not None
        for ticker in all_tickers:
            assert ticker in result

    def test_returns_none_when_download_raises(self):
        provider = PolicyFeatureProvider()
        with patch(
            "trading.features.policy_feature_provider.yf.download",
            side_effect=RuntimeError("network error"),
        ):
            result = provider._fetch_etf_returns()
        assert result is None

    def test_returns_none_when_close_too_short(self):
        all_tickers = list(_DEFENSIVE_ETFS) + [_EQUITY_BENCHMARK]
        raw = _make_raw_download(all_tickers, rows=POLICY_MIN_OBSERVATIONS - 1)

        provider = PolicyFeatureProvider()
        with patch("trading.features.policy_feature_provider.yf.download", return_value=raw):
            result = provider._fetch_etf_returns()
        assert result is None

    def test_returns_none_on_empty_download(self):
        provider = PolicyFeatureProvider()
        with patch(
            "trading.features.policy_feature_provider.yf.download",
            return_value=pd.DataFrame(),
        ):
            result = provider._fetch_etf_returns()
        assert result is None


# ---------------------------------------------------------------------------
# PolicyFeatureProvider — _fetch (bundle computation)
# ---------------------------------------------------------------------------


class TestPolicyFeatureProviderFetch:
    def _provider_with_returns(self, spy_ret: float, defensive_rets: dict[str, float]):
        """Build a provider whose _fetch_etf_returns is patched to return fixed data."""
        provider = PolicyFeatureProvider()
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
        provider = PolicyFeatureProvider()
        provider._fetch_etf_returns = MagicMock(
            return_value={"TLT": 0.02, "GLD": 0.01, "XLU": 0.01, "UUP": 0.00}
            # SPY intentionally absent
        )
        bundle = provider._fetch("ANY")
        assert bundle.available is False

    def test_unavailable_when_all_defensives_missing(self):
        provider = PolicyFeatureProvider()
        provider._fetch_etf_returns = MagicMock(
            return_value={_EQUITY_BENCHMARK: 0.05}
            # no defensive ETFs
        )
        bundle = provider._fetch("ANY")
        assert bundle.available is False

    def test_unavailable_when_returns_none(self):
        provider = PolicyFeatureProvider()
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
        provider = PolicyFeatureProvider()
        provider._fetch_etf_returns = MagicMock(
            return_value={
                _EQUITY_BENCHMARK: 0.03,
                "TLT": 0.01, "GLD": 0.01, "XLU": 0.01, "UUP": 0.01,
            }
        )
        b1 = provider.get_features("AAPL")
        b2 = provider.get_features("MSFT")
        assert b1 is b2
        assert provider._fetch_etf_returns.call_count == 1


# ---------------------------------------------------------------------------
# _policy_regime_signal
# ---------------------------------------------------------------------------


class TestPolicyRegimeSignal:
    def test_buy_when_trend_up_and_risk_on(self):
        history = _make_history(n=60, start=100.0, slope=1.0)
        fh = _make_feature_history(risk_on=0.70, def_tilt=-0.01)
        assert _policy_regime_signal(history, {}, fh) == "buy"

    def test_hold_when_features_missing(self):
        history = _make_history(n=60, start=100.0, slope=1.0)
        assert _policy_regime_signal(history, {}, None) == "hold"

    def test_hold_when_history_too_short(self):
        history = _make_history(n=10)
        fh = _make_feature_history(risk_on=0.70, def_tilt=-0.01)
        assert _policy_regime_signal(history, {}, fh) == "hold"

    def test_sell_when_trend_down(self):
        # Declining prices → sma_slow > close
        history = _make_history(n=60, start=200.0, slope=-2.0)
        fh = _make_feature_history(risk_on=0.70, def_tilt=-0.01)
        signal = _policy_regime_signal(history, {}, fh)
        assert signal == "sell"

    def test_sell_when_risk_off(self):
        history = _make_history(n=60, start=100.0, slope=1.0)
        fh = _make_feature_history(risk_on=0.30, def_tilt=0.05)
        signal = _policy_regime_signal(history, {}, fh)
        assert signal == "sell"

    def test_hold_on_neutral_score(self):
        history = _make_history(n=60, start=100.0, slope=0.2)
        fh = _make_feature_history(risk_on=0.50, def_tilt=0.01)
        signal = _policy_regime_signal(history, {}, fh)
        # risk_on 0.50 < risk_on_threshold 0.55 → no buy; close > sma_slow → no sell
        assert signal in ("hold", "sell")

    def test_custom_params_respected(self):
        history = _make_history(n=60, start=100.0, slope=1.0)
        fh = _make_feature_history(risk_on=0.60, def_tilt=-0.01)
        # Raise threshold above the score → should NOT buy
        params = {"risk_on_threshold": 0.80}
        signal = _policy_regime_signal(history, params, fh)
        assert signal != "buy"


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestPolicyRegimeRegistryEntry:
    def test_registered_in_strategy_registry(self):
        assert "policy_regime" in STRATEGY_REGISTRY

    def test_strategy_style_is_alternative(self):
        spec = STRATEGY_REGISTRY["policy_regime"]
        assert spec.strategy_style == "alternative"

    def test_required_features_declared(self):
        spec = STRATEGY_REGISTRY["policy_regime"]
        assert POLICY_RISK_ON_SCORE in spec.required_features
        assert POLICY_DEFENSIVE_TILT in spec.required_features

    def test_aliases_resolve_correctly(self):
        for alias in ("policy_external", "policy_etf", "political_regime"):
            spec = resolve_strategy(alias)
            assert spec.strategy_id == "policy_regime"

    def test_keyword_resolve_political(self):
        spec = resolve_strategy("political_macro")
        assert spec.strategy_id == "policy_regime"

    def test_plain_policy_routes_to_macro_not_policy_regime(self):
        # "policy" alone must route to macro_proxy_regime, not policy_regime.
        # _resolve_by_keyword checks "policy_regime" before "policy" — this
        # test guards against accidental reordering.
        spec = resolve_strategy("policy")
        assert spec.strategy_id == "macro_proxy_regime"
