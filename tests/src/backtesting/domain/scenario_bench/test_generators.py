"""A generator must be deterministic in its seed and produce valid OHLC bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtesting.domain.scenario_bench.contracts import PathRequest
from backtesting.domain.scenario_bench.generators import gbm_regime, regime_switch
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN

_TICKERS = ("SYN1", "SYN2")
_INDEX = pd.bdate_range(start="2024-01-01", periods=120)


def _uptrend_request(seed: int) -> PathRequest:
    return PathRequest(
        index=_INDEX,
        tickers=_TICKERS,
        seed=seed,
        params={"annual_drift": 0.3, "annual_vol": 0.2},
    )


def _assert_valid_ohlc(frame: pd.DataFrame) -> None:
    assert list(frame.columns) == list(BAR_COLUMNS)
    highest_of_body = frame[[BAR_OPEN, BAR_CLOSE]].max(axis=1)
    lowest_of_body = frame[[BAR_OPEN, BAR_CLOSE]].min(axis=1)
    assert (frame[BAR_HIGH] >= highest_of_body - 1e-9).all()
    assert (frame[BAR_LOW] <= lowest_of_body + 1e-9).all()
    assert (frame[BAR_HIGH] >= frame[BAR_LOW]).all()
    assert (frame[BAR_CLOSE] > 0).all()


class TestGbmRegime:
    def test_same_seed_rebuilds_identical_bars(self) -> None:
        first = gbm_regime(_uptrend_request(42))
        second = gbm_regime(_uptrend_request(42))
        for ticker in _TICKERS:
            pd.testing.assert_frame_equal(first[ticker], second[ticker])

    def test_different_seed_changes_the_path(self) -> None:
        first = gbm_regime(_uptrend_request(1))
        second = gbm_regime(_uptrend_request(2))
        assert not first["SYN1"][BAR_CLOSE].equals(second["SYN1"][BAR_CLOSE])

    def test_every_frame_is_valid_ohlc_over_the_requested_calendar(self) -> None:
        frames = gbm_regime(_uptrend_request(7))
        for ticker in _TICKERS:
            frame = frames[ticker]
            assert len(frame) == len(_INDEX)
            assert frame.index.equals(_INDEX)
            _assert_valid_ohlc(frame)

    def test_positive_drift_rises_on_average_over_many_seeds(self) -> None:
        ending_multiples = [
            gbm_regime(_uptrend_request(seed))["SYN1"][BAR_CLOSE].iloc[-1]
            / gbm_regime(_uptrend_request(seed))["SYN1"][BAR_CLOSE].iloc[0]
            for seed in range(40)
        ]
        assert float(np.mean(ending_multiples)) > 1.0

    def test_strong_negative_drift_falls_on_average_over_many_seeds(self) -> None:
        crash_multiples = []
        for seed in range(40):
            request = PathRequest(
                index=_INDEX,
                tickers=("SYN1",),
                seed=seed,
                params={"annual_drift": -0.9, "annual_vol": 0.5},
            )
            closes = gbm_regime(request)["SYN1"][BAR_CLOSE]
            crash_multiples.append(closes.iloc[-1] / closes.iloc[0])
        assert float(np.mean(crash_multiples)) < 1.0


class TestRegimeSwitch:
    def _switch_request(self, seed: int) -> PathRequest:
        return PathRequest(
            index=_INDEX,
            tickers=("SYN1",),
            seed=seed,
            params={
                "phase1_drift": 0.4,
                "phase1_vol": 0.15,
                "phase2_drift": -1.2,
                "phase2_vol": 0.6,
                "switch_fraction": 0.7,
            },
        )

    def test_joined_series_is_continuous_and_valid(self) -> None:
        frame = regime_switch(self._switch_request(3))["SYN1"]
        assert len(frame) == len(_INDEX)
        _assert_valid_ohlc(frame)

    def test_same_seed_rebuilds_identically(self) -> None:
        first = regime_switch(self._switch_request(9))["SYN1"]
        second = regime_switch(self._switch_request(9))["SYN1"]
        pd.testing.assert_frame_equal(first, second)
