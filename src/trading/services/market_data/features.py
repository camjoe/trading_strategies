from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Mapping

import pandas as pd

from common.tickers import load_ticker_categories

from .protocols import FeatureBundle
from .protocols import FeatureDataProvider
from .protocols import MarketDataProvider
from .protocols import require_provider


class ProxyFeatureDataProvider(FeatureDataProvider):
    """Free-first proxy feature provider using sector ETFs and market-risk series."""

    def __init__(
        self,
        *,
        category_file: str = "trends/assets/ticker_categories.txt",
        category_proxy_map: Mapping[str, str] | None = None,
        topic_lookback: int = 20,
        macro_lookback: int = 20,
        market_data_provider: MarketDataProvider | None = None,
    ) -> None:
        self._market_data_provider = market_data_provider
        self.category_file = category_file
        self.category_proxy_map = {
            "tech": "XLK",
            "technology": "XLK",
            "energy": "XLE",
            "banks": "XLF",
            "financials": "XLF",
            "etf": "SPY",
            **{(key.strip().lower()): value.strip().upper() for key, value in (category_proxy_map or {}).items()},
        }
        self.topic_lookback = topic_lookback
        self.macro_lookback = macro_lookback

    def _load_proxy_map(self, tickers: list[str]) -> tuple[dict[str, str], list[str]]:
        warnings: list[str] = []
        ticker_to_proxy: dict[str, str] = {}
        category_path = Path(self.category_file)
        if category_path.exists():
            categories = load_ticker_categories(str(category_path))
            for category, category_tickers in categories.items():
                proxy = self.category_proxy_map.get(category)
                if proxy is None:
                    continue
                for ticker in category_tickers:
                    ticker_to_proxy.setdefault(ticker.upper(), proxy)
        else:
            warnings.append(
                f"Category file '{self.category_file}' not found;"
                " topic proxy mappings will only be available for proxy ETFs in the universe."
            )

        known_proxies = set(self.category_proxy_map.values()) | {"SPY", "QQQ", "IWM", "TLT"}
        for ticker in tickers:
            upper = ticker.upper()
            if upper in known_proxies:
                ticker_to_proxy.setdefault(upper, upper)

        return ticker_to_proxy, warnings

    def build_feature_bundle(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
        close_history: pd.DataFrame,
    ) -> FeatureBundle:
        if close_history.empty:
            return FeatureBundle(ticker_features={})

        ticker_to_proxy, warnings = self._load_proxy_map(tickers)
        proxy_tickers = sorted(set(ticker_to_proxy.values()) | {"SPY", "TLT", "^VIX"})
        padded_start = start_date - timedelta(days=max(self.topic_lookback, self.macro_lookback) * 4)

        provider = require_provider(self._market_data_provider)
        try:
            proxy_close = provider.fetch_close_history(proxy_tickers, padded_start, end_date)
        except Exception as exc:
            return FeatureBundle(
                ticker_features={},
                warnings=tuple(warnings + [f"Proxy feature data unavailable: {exc}"]),
            )

        target_index = pd.to_datetime(close_history.index)
        if getattr(target_index, "tz", None) is not None:
            target_index = target_index.tz_convert(None)
        proxy_close = proxy_close.reindex(target_index).ffill()

        topic_returns = proxy_close.pct_change(self.topic_lookback)
        topic_trend_gap = (proxy_close / proxy_close.rolling(self.topic_lookback).mean()) - 1.0

        equity_bond_spread = proxy_close["SPY"].pct_change(self.macro_lookback) - proxy_close["TLT"].pct_change(
            self.macro_lookback
        )
        vix_pressure = (proxy_close["^VIX"] / proxy_close["^VIX"].rolling(self.macro_lookback).mean()) - 1.0
        macro_risk_on_score = equity_bond_spread - vix_pressure.fillna(0.0)

        market_features = pd.DataFrame(
            {
                "macro_equity_bond_spread": equity_bond_spread,
                "macro_vix_pressure": vix_pressure,
                "macro_risk_on_score": macro_risk_on_score,
            },
            index=target_index,
        )

        unmapped: list[str] = []
        ticker_features: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            frame = market_features.copy()
            proxy_ticker = ticker_to_proxy.get(ticker.upper())
            if proxy_ticker and proxy_ticker in proxy_close.columns:
                frame["topic_proxy_rel_strength"] = topic_returns[proxy_ticker] - topic_returns["SPY"]
                frame["topic_proxy_trend_gap"] = topic_trend_gap[proxy_ticker]
                frame["topic_proxy_available"] = 1.0
            else:
                unmapped.append(ticker)
                frame["topic_proxy_rel_strength"] = float("nan")
                frame["topic_proxy_trend_gap"] = float("nan")
                frame["topic_proxy_available"] = 0.0
            ticker_features[ticker] = frame

        if unmapped:
            warnings.append("Topic proxy mappings were unavailable for: " + ", ".join(sorted(unmapped)))

        warnings.append(
            "Proxy features use sector/theme ETFs plus SPY, TLT, and ^VIX"
            " as free-first substitutes for topic and macro sentiment."
        )

        return FeatureBundle(
            ticker_features=ticker_features,
            market_features=market_features,
            warnings=tuple(warnings),
        )
