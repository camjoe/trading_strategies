"""The gap-filling rules a daily bar frame obeys, for one ticker.

A vendor returns a ticker's bars on whatever calendar it traded, with its own
column spelling and whatever gaps the tape had. Two readers of that frame — the
simulation engine and the live runtime — have to agree on what a gap means, or
the same strategy evaluates differently in a backtest than it does against the
market. That agreement is this module.

Multi-ticker calendar alignment is a separate concern and lives with the engine
that walks a calendar (``trading.backtesting.domain.bars``); this is the
per-frame rule both paths share.

Pure derivation: no provider, no connection, no I/O.
"""

from __future__ import annotations

import pandas as pd

from trading.models.market_data import BAR_COLUMNS, BAR_PRICE_COLUMNS, BAR_VOLUME, BAR_VOLUME_FILL


def normalize_bar_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return *frame* sorted, tz-naive, gap-filled, and in ``BAR_COLUMNS`` order.

    Prices carry forward across days the ticker did not trade — the last trade
    stays the best estimate of value. Volume does not: a repeated volume would
    assert trading that never happened, so gaps become ``BAR_VOLUME_FILL``.

    Leading rows are dropped rather than back-filled. Before a ticker's first
    bar there is nothing to carry forward, and inventing a price that predates
    the listing would let a strategy trade on it.

    Raises ``KeyError`` if a bar column is missing — a frame that cannot obey
    the contract should not be silently reshaped into something that looks like
    it does.
    """
    missing = [column for column in BAR_COLUMNS if column not in frame.columns]
    if missing:
        raise KeyError(f"Bar frame is missing required column(s): {', '.join(missing)}")

    frame = frame.sort_index()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    prices = frame[list(BAR_PRICE_COLUMNS)].ffill().dropna(how="any")
    cleaned = prices.copy()
    cleaned[BAR_VOLUME] = frame[BAR_VOLUME].reindex(prices.index).fillna(BAR_VOLUME_FILL)
    return cleaned[list(BAR_COLUMNS)]
