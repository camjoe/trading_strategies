"""Synthetic price-path generators for the scenario bench.

Each generator is a pure function of a :class:`PathRequest`. It is deterministic
in the request's seed, so a scenario's path N rebuilds identically every run. The
bars obey the OHLC invariants (``high >= max(open, close)``,
``low <= min(open, close)``), so the simulation engine prices them like any real
frame.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from common.constants import TRADING_DAYS_PER_YEAR
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME

from .contracts import PathRequest

# Moving-block length in trading days when a bootstrap scenario does not set one.
# One month of blocks keeps short-run autocorrelation (a trend or a sell-off runs
# for several days) that an independent day-by-day resample would destroy.
DEFAULT_BLOCK_SIZE = 20

# Per-ticker starting price when a scenario does not set one.
DEFAULT_START_PRICE = 100.0
# Intraday range as a fraction of price, used to extend the high and low beyond
# the open/close range when a scenario does not set one.
DEFAULT_INTRADAY_RANGE_PCT = 0.01
# Synthetic daily volume band. Liquidity is not modeled; a plausible non-zero
# volume keeps a volume-reading filter from tripping on a zero.
BASE_VOLUME = 1_000_000.0
VOLUME_JITTER = 500_000.0
# Fraction of the window where a two-phase scenario switches regime, when the
# scenario does not set one.
DEFAULT_SWITCH_FRACTION = 0.5


def _ticker_seed(seed: int, ticker: str) -> list[int]:
    """A per-ticker seed sequence, so tickers differ within a path.

    The ticker digest spreads the tickers apart; the path seed spreads the paths
    apart. Both go into the generator's ``default_rng`` seed sequence.
    """
    digest = hashlib.sha256(ticker.encode("utf-8")).digest()
    return [int(seed), int.from_bytes(digest[:8], "big")]


def _gbm_closes(
    rng: np.random.Generator,
    days: int,
    start_price: float,
    annual_drift: float,
    annual_vol: float,
) -> np.ndarray:
    """A geometric-Brownian-motion close series over *days* trading days."""
    dt = 1.0 / float(TRADING_DAYS_PER_YEAR)
    shocks = rng.standard_normal(days)
    log_steps = (annual_drift - 0.5 * annual_vol**2) * dt + annual_vol * np.sqrt(dt) * shocks
    return start_price * np.exp(np.cumsum(log_steps))


def _bars_from_closes(
    rng: np.random.Generator,
    closes: np.ndarray,
    index: pd.DatetimeIndex,
    intraday_range_pct: float,
) -> pd.DataFrame:
    """Wrap a close series in OHLCV bars that obey the OHLC invariants.

    The open is the prior close. The high and low extend beyond the open/close
    range by a non-negative random fraction, so the high never sits below either
    and the low never sits above either.
    """
    opens = np.empty_like(closes)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]
    high_base = np.maximum(opens, closes)
    low_base = np.minimum(opens, closes)
    highs = high_base * (1.0 + intraday_range_pct * rng.random(len(closes)))
    lows = low_base * (1.0 - intraday_range_pct * rng.random(len(closes)))
    volume = BASE_VOLUME + VOLUME_JITTER * rng.random(len(closes))
    frame = pd.DataFrame(
        {
            BAR_OPEN: opens,
            BAR_HIGH: highs,
            BAR_LOW: lows,
            BAR_CLOSE: closes,
            BAR_VOLUME: volume,
        },
        index=index,
    )
    return frame[list(BAR_COLUMNS)]


def gbm_regime(request: PathRequest) -> dict[str, pd.DataFrame]:
    """One geometric-Brownian-motion regime for every requested ticker.

    Reads ``annual_drift`` and ``annual_vol`` from the scenario params, plus
    optional ``start_price`` and ``intraday_range_pct``.
    """
    params = request.params
    start_price = float(params.get("start_price", DEFAULT_START_PRICE))
    annual_drift = float(params["annual_drift"])
    annual_vol = float(params["annual_vol"])
    intraday = float(params.get("intraday_range_pct", DEFAULT_INTRADAY_RANGE_PCT))
    days = len(request.index)

    frames: dict[str, pd.DataFrame] = {}
    for ticker in request.tickers:
        rng = np.random.default_rng(_ticker_seed(request.seed, ticker))
        closes = _gbm_closes(rng, days, start_price, annual_drift, annual_vol)
        frames[ticker] = _bars_from_closes(rng, closes, request.index, intraday)
    return frames


def regime_switch(request: PathRequest) -> dict[str, pd.DataFrame]:
    """Two regimes joined at ``switch_fraction`` of the window.

    Reads ``phase1_drift``/``phase1_vol`` and ``phase2_drift``/``phase2_vol`` from
    the scenario params, plus optional ``switch_fraction``, ``start_price``, and
    ``intraday_range_pct``. The second phase starts from the first phase's last
    close, so the joined series is continuous.
    """
    params = request.params
    start_price = float(params.get("start_price", DEFAULT_START_PRICE))
    intraday = float(params.get("intraday_range_pct", DEFAULT_INTRADAY_RANGE_PCT))
    switch_fraction = float(params.get("switch_fraction", DEFAULT_SWITCH_FRACTION))
    days = len(request.index)
    split = max(1, min(days - 1, int(days * switch_fraction)))

    frames: dict[str, pd.DataFrame] = {}
    for ticker in request.tickers:
        rng = np.random.default_rng(_ticker_seed(request.seed, ticker))
        first = _gbm_closes(rng, split, start_price, float(params["phase1_drift"]), float(params["phase1_vol"]))
        second = _gbm_closes(
            rng,
            days - split,
            float(first[-1]),
            float(params["phase2_drift"]),
            float(params["phase2_vol"]),
        )
        closes = np.concatenate([first, second])
        frames[ticker] = _bars_from_closes(rng, closes, request.index, intraday)
    return frames


def unbound_generator(request: PathRequest) -> dict[str, pd.DataFrame]:
    """The placeholder a real-data scenario carries until the seam binds it.

    A real-data scenario declares a fixture, not a callable. The composition seam
    loads the fixture and replaces this with a bound replay/bootstrap generator, so
    reaching this means a real-data scenario ran without going through that seam.
    """
    raise ValueError(
        "Real-data scenario generator was not bound; run real-data scenarios through composition.run_bench."
    )


def replay_frames(
    bars: Mapping[str, pd.DataFrame],
    tickers: Sequence[str],
    index: pd.DatetimeIndex,
) -> dict[str, pd.DataFrame]:
    """Serve frozen fixture bars as one path, re-stamped onto the bench calendar.

    Replay is deterministic: the real bars are the path. Their real dates are
    replaced with the anchored bench calendar so the run's window is synthetic like
    every other scenario; the prices and ranges are the real ones.
    """
    frames: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        frame = bars[ticker]
        if len(frame) != len(index):
            raise ValueError(
                f"Replay fixture length {len(frame)} does not match scenario days {len(index)} for {ticker}."
            )
        frames[ticker] = frame.set_axis(index, axis=0)[list(BAR_COLUMNS)]
    return frames


def _day_ratios(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Each real bar's open/high/low/close as ratios to the prior close, plus volume.

    Rebuilding a path from these ratios preserves every real day's return and its
    intraday geometry, so a resampled bar is shaped like a bar the market printed.
    """
    close = frame[BAR_CLOSE].to_numpy(dtype=float)
    open_ = frame[BAR_OPEN].to_numpy(dtype=float)
    high = frame[BAR_HIGH].to_numpy(dtype=float)
    low = frame[BAR_LOW].to_numpy(dtype=float)
    prev_close = np.empty_like(close)
    # The first bar has no prior close, so measure its ratios against its own open.
    prev_close[0] = open_[0]
    prev_close[1:] = close[:-1]
    return {
        "open": open_ / prev_close,
        "high": high / prev_close,
        "low": low / prev_close,
        "close": close / prev_close,
        "volume": frame[BAR_VOLUME].to_numpy(dtype=float),
        "base": np.array([close[0]], dtype=float),
    }


def _block_positions(rng: np.random.Generator, source_len: int, target: int, block_size: int) -> list[int]:
    """A moving-block resample of source row positions, length *target*.

    Whole blocks of consecutive days are drawn, so a run of days (a trend, a
    sell-off) is kept intact rather than shuffled away.
    """
    block = max(1, min(block_size, source_len))
    positions: list[int] = []
    while len(positions) < target:
        start = int(rng.integers(0, source_len - block + 1))
        positions.extend(range(start, start + block))
    return positions[:target]


def bootstrap_frames(
    bars: Mapping[str, pd.DataFrame],
    tickers: Sequence[str],
    index: pd.DatetimeIndex,
    seed: int,
    block_size: int,
) -> dict[str, pd.DataFrame]:
    """Block-bootstrap real bars into one path over the bench calendar.

    One block sequence is drawn per path and shared by every ticker, so the sampled
    days keep their cross-ticker co-movement — a real correlated sell-off stays
    correlated. Each ticker's path chains its own real per-day ratios off that
    shared sequence.
    """
    target = len(index)
    source_len = min(len(bars[ticker]) for ticker in tickers)
    rng = np.random.default_rng([int(seed)])
    positions = _block_positions(rng, source_len, target, block_size or DEFAULT_BLOCK_SIZE)

    frames: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        ratios = _day_ratios(bars[ticker])
        opens = np.empty(target)
        highs = np.empty(target)
        lows = np.empty(target)
        closes = np.empty(target)
        volume = np.empty(target)
        prev = float(ratios["base"][0])
        for i, position in enumerate(positions):
            opens[i] = prev * ratios["open"][position]
            highs[i] = prev * ratios["high"][position]
            lows[i] = prev * ratios["low"][position]
            closes[i] = prev * ratios["close"][position]
            volume[i] = ratios["volume"][position]
            prev = closes[i]
        frame = pd.DataFrame(
            {BAR_OPEN: opens, BAR_HIGH: highs, BAR_LOW: lows, BAR_CLOSE: closes, BAR_VOLUME: volume},
            index=index,
        )
        frames[ticker] = frame[list(BAR_COLUMNS)]
    return frames
