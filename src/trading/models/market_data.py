"""Market-data vocabulary."""

from __future__ import annotations

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
