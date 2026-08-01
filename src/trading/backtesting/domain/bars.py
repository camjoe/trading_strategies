"""Align per-ticker bar frames onto one trading calendar.

A provider returns each ticker's bars on that ticker's own index — they differ
whenever a name listed late, was halted, or simply did not trade. A simulation
walks one calendar, so the engine needs a single ordered set of dates and, for
any date, every ticker's bar.

Pure derivation: no I/O, no provider, no connection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from trading.models.market_data.constants import (
    BAR_CLOSE,
    BAR_PRICE_COLUMNS,
    BAR_VOLUME,
    BAR_VOLUME_FILL,
)


@dataclass(frozen=True)
class BarPanel:
    """Every requested ticker's bars, reindexed to one shared calendar.

    ``close`` is the ticker-per-column view the simulation prices and marks at;
    ``frames`` keeps each ticker's full bar frame on that same calendar, for
    anything that needs the range rather than the endpoint.

    ``sources`` keeps each ticker's bars on *its own* trading days, before
    alignment. Indicators are computed from these rather than from ``frames``:
    the shared calendar contains days a given ticker did not trade, and a
    rolling window over those carried-forward rows makes one ticker's indicator
    depend on which *other* tickers are in the universe. See
    ``build_signal_inputs``.
    """

    dates: list[pd.Timestamp]
    frames: dict[str, pd.DataFrame]
    close: pd.DataFrame
    sources: dict[str, pd.DataFrame]

    def frame(self, ticker: str) -> pd.DataFrame:
        """One ticker's bars on the shared calendar — for pricing and marking."""
        return self.frames[ticker]

    def source(self, ticker: str) -> pd.DataFrame:
        """One ticker's bars on its own trading days — for indicators."""
        return self.sources[ticker]


def build_bar_panel(frames: Mapping[str, pd.DataFrame], tickers: Sequence[str]) -> BarPanel:
    """Reindex *tickers*' bar frames onto the union of their trading days.

    The calendar is the union rather than the intersection so a ticker that
    stops trading does not truncate the run for everything else.

    On a day a ticker has no bar, its prices carry forward and its volume is
    zero — the same rule the adapters apply within a single ticker's history,
    extended to days that only other tickers traded. Days before a ticker's
    first bar stay empty: there is nothing to carry forward, and back-filling
    would invent prices that predate the listing.
    """
    missing = [ticker for ticker in tickers if ticker not in frames]
    if missing:
        raise ValueError(f"Missing bar history for tickers: {', '.join(sorted(missing))}")

    calendar = pd.DatetimeIndex([])
    for ticker in tickers:
        calendar = calendar.union(frames[ticker].index)
    calendar = calendar.sort_values()

    aligned: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        frame = frames[ticker].reindex(calendar)
        prices = frame[list(BAR_PRICE_COLUMNS)].ffill()
        prices[BAR_VOLUME] = frame[BAR_VOLUME].fillna(BAR_VOLUME_FILL)
        aligned[ticker] = prices

    close = pd.DataFrame({ticker: aligned[ticker][BAR_CLOSE] for ticker in tickers}, index=calendar)
    return BarPanel(
        dates=list(calendar),
        frames=aligned,
        close=close,
        sources={ticker: frames[ticker] for ticker in tickers},
    )
