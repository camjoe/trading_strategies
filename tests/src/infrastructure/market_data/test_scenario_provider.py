"""The scenario provider serves a materialized bar-set and slices it to a window."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from infrastructure.market_data.scenario_provider import ScenarioMarketDataProvider
from trading.models.market_data import BAR_COLUMNS


def _frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({column: [1.0] * len(index) for column in BAR_COLUMNS}, index=index)[list(BAR_COLUMNS)]


class TestScenarioMarketDataProvider:
    def test_slices_to_the_window_and_returns_only_requested_tickers(self) -> None:
        index = pd.bdate_range("2000-01-03", periods=10)
        provider = ScenarioMarketDataProvider({"SYN1": _frame(index), "BENCH": _frame(index)})

        frames = provider.fetch_bar_history(["SYN1"], index[2].date(), index[5].date())

        assert set(frames) == {"SYN1"}
        # Inclusive slice of positions 2..5.
        assert len(frames["SYN1"]) == 4

    def test_missing_ticker_raises(self) -> None:
        index = pd.bdate_range("2000-01-03", periods=5)
        provider = ScenarioMarketDataProvider({"SYN1": _frame(index)})

        with pytest.raises(ValueError, match="no generated bars"):
            provider.fetch_bar_history(["MISSING"], index[0].date(), index[-1].date())

    def test_empty_tickers_raises(self) -> None:
        provider = ScenarioMarketDataProvider({})
        with pytest.raises(ValueError):
            provider.fetch_bar_history([], date(2000, 1, 3), date(2000, 1, 10))
