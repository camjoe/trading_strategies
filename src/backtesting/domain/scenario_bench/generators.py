"""Synthetic price-path generators for the scenario bench.

Each generator is a pure function of a :class:`PathRequest`. It is deterministic
in the request's seed, so a scenario's path N rebuilds identically every run. The
bars obey the OHLC invariants (``high >= max(open, close)``,
``low <= min(open, close)``), so the simulation engine prices them like any real
frame.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from common.constants import TRADING_DAYS_PER_YEAR
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME

from .contracts import PathRequest

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
