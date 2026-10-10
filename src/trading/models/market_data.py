"""Market-data vocabulary and the per-run market input bundle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

BAR_OPEN = "open"
BAR_HIGH = "high"
BAR_LOW = "low"
BAR_CLOSE = "close"
BAR_VOLUME = "volume"

# The exact column set every bar frame carries, in conventional order. Adapters
# produce all five; consumers may rely on all five being present.
BAR_COLUMNS = (BAR_OPEN, BAR_HIGH, BAR_LOW, BAR_CLOSE, BAR_VOLUME)

# The four price columns, as distinct from volume. They share a unit (currency
# per share) and a fill rule; volume shares neither, which is why the split is
# named rather than written out at each use.
BAR_PRICE_COLUMNS = (BAR_OPEN, BAR_HIGH, BAR_LOW, BAR_CLOSE)

# Volume on a day a ticker did not trade is zero, not "the same as yesterday".
# Prices carry forward because the last trade remains the best estimate of value;
# repeating a volume would assert trading that never happened, and any liquidity
# filter reading it would be reading an invention.
BAR_VOLUME_FILL = 0.0


@dataclass(frozen=True, slots=True)
class MarketInputs:
    """The market data one auto-trading run fetched, shared by every account and book.

    Fetched once per run and read-only from there: `frozen` stops rebinding, but the
    mapped prices and frames are shared, not copied, so callers must not mutate them.

    `universe` is the run-wide fetch set. A book selects over its own stored symbols
    when it has any and falls back to this list when it does not, so every symbol a
    book can pick has to be priced here.
    """

    universe: list[str]
    prices: dict[str, float]
    # Empty when no option/leaps book is trading — the proxy is only read for those.
    iv_rank_proxy: dict[str, float] = field(default_factory=dict)
    # Bar frames carry BAR_COLUMNS. Empty means no signal can be evaluated.
    histories: Mapping[str, pd.DataFrame] = field(default_factory=dict)
