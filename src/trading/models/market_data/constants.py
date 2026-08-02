"""Data-contract vocabulary for daily bar frames.

A *bar* is one ticker's trading for one day: the first and last traded prices,
the extremes reached in between, and the shares that changed hands. Close-only
history gives the endpoints; a bar also gives the range the price travelled to
reach them, which is what makes true-range volatility, high/low breakouts, and
any judgement about whether a stop level was reached expressible at all.

Column names are lower-case here even though the market-data vendor emits
capitalized ones. Adapters normalize on the way in, so nothing above the
infrastructure layer has to know whose spelling it is looking at.
"""

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
