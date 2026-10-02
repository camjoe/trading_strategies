"""Fixtures round-trip through the CSV loader, and a missing one raises."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import backtesting.services.scenario_fixtures as scenario_fixtures
from trading.domain.exceptions import ValidationError
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME


def _bars(periods: int) -> pd.DataFrame:
    index = pd.bdate_range("2020-01-02", periods=periods)
    close = np.linspace(100.0, 120.0, periods)
    frame = pd.DataFrame(
        {
            BAR_OPEN: close,
            BAR_HIGH: close * 1.01,
            BAR_LOW: close * 0.99,
            BAR_CLOSE: close,
            BAR_VOLUME: np.full(periods, 1_000_000.0),
        },
        index=index,
    )
    return frame[list(BAR_COLUMNS)]


class TestFixtureRoundTrip:
    def test_save_then_load_preserves_bars(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(scenario_fixtures, "SCENARIO_BENCH_FIXTURES_DIR", tmp_path)
        frames = {"RT1": _bars(20), "RB": _bars(20)}

        path = scenario_fixtures.save_fixture("episode", frames)
        assert path.exists()

        loaded = scenario_fixtures.load_fixture("episode")
        assert set(loaded) == {"RT1", "RB"}
        for ticker in frames:
            assert list(loaded[ticker].columns) == list(BAR_COLUMNS)
            assert np.allclose(loaded[ticker][BAR_CLOSE].to_numpy(), frames[ticker][BAR_CLOSE].to_numpy())

    def test_missing_fixture_raises_with_capture_hint(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(scenario_fixtures, "SCENARIO_BENCH_FIXTURES_DIR", tmp_path)
        with pytest.raises(ValidationError, match="capture_scenario_fixture"):
            scenario_fixtures.load_fixture("absent")
