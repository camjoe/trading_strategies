"""Replay serves the real bars; bootstrap resamples them, seeded and OHLC-valid."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.domain.scenario_bench.contracts import PathRequest
from backtesting.domain.scenario_bench.generators import (
    bootstrap_frames,
    replay_frames,
    unbound_generator,
)
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME


def _real_bars(seed: int, periods: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2020-01-02", periods=periods)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.02, periods))
    open_ = np.concatenate([[close[0]], close[:-1]])
    pair_high = np.maximum(open_, close) * 1.01
    pair_low = np.minimum(open_, close) * 0.99
    frame = pd.DataFrame(
        {
            BAR_OPEN: open_,
            BAR_HIGH: pair_high,
            BAR_LOW: pair_low,
            BAR_CLOSE: close,
            BAR_VOLUME: rng.integers(1_000_000, 5_000_000, periods).astype(float),
        },
        index=index,
    )
    return frame[list(BAR_COLUMNS)]


def _assert_valid_ohlc(frame: pd.DataFrame) -> None:
    body_high = frame[[BAR_OPEN, BAR_CLOSE]].max(axis=1)
    body_low = frame[[BAR_OPEN, BAR_CLOSE]].min(axis=1)
    assert (frame[BAR_HIGH] >= body_high - 1e-9).all()
    assert (frame[BAR_LOW] <= body_low + 1e-9).all()
    assert (frame[BAR_CLOSE] > 0).all()


class TestUnboundGenerator:
    def test_raises_until_bound(self) -> None:
        request = PathRequest(index=pd.bdate_range("2024-01-01", periods=3), tickers=("X",), seed=1, params={})
        with pytest.raises(ValueError, match="not bound"):
            unbound_generator(request)


class TestReplayFrames:
    def test_restamps_real_bars_onto_the_target_calendar(self) -> None:
        bars = {"RT1": _real_bars(1, 30), "RB": _real_bars(2, 30)}
        index = pd.bdate_range("2000-01-03", periods=30)

        frames = replay_frames(bars, ("RT1", "RB"), index)

        assert set(frames) == {"RT1", "RB"}
        assert frames["RT1"].index.equals(index)
        # The prices are the real ones, only the dates changed.
        assert np.allclose(frames["RT1"][BAR_CLOSE].to_numpy(), bars["RT1"][BAR_CLOSE].to_numpy())

    def test_length_mismatch_raises(self) -> None:
        bars = {"RT1": _real_bars(1, 30)}
        index = pd.bdate_range("2000-01-03", periods=25)
        with pytest.raises(ValueError, match="does not match"):
            replay_frames(bars, ("RT1",), index)


class TestBootstrapFrames:
    def test_same_seed_rebuilds_identically(self) -> None:
        bars = {"RT1": _real_bars(1, 120), "RT2": _real_bars(2, 120)}
        index = pd.bdate_range("2000-01-03", periods=60)

        first = bootstrap_frames(bars, ("RT1", "RT2"), index, seed=7, block_size=20)
        second = bootstrap_frames(bars, ("RT1", "RT2"), index, seed=7, block_size=20)

        for ticker in ("RT1", "RT2"):
            pd.testing.assert_frame_equal(first[ticker], second[ticker])

    def test_produces_valid_ohlc_of_the_requested_length(self) -> None:
        bars = {"RT1": _real_bars(1, 120)}
        index = pd.bdate_range("2000-01-03", periods=60)

        frames = bootstrap_frames(bars, ("RT1",), index, seed=3, block_size=20)

        assert len(frames["RT1"]) == 60
        assert frames["RT1"].index.equals(index)
        _assert_valid_ohlc(frames["RT1"])

    def test_different_seed_changes_the_path(self) -> None:
        bars = {"RT1": _real_bars(1, 120)}
        index = pd.bdate_range("2000-01-03", periods=60)

        first = bootstrap_frames(bars, ("RT1",), index, seed=1, block_size=20)
        second = bootstrap_frames(bars, ("RT1",), index, seed=2, block_size=20)

        assert not first["RT1"][BAR_CLOSE].equals(second["RT1"][BAR_CLOSE])
