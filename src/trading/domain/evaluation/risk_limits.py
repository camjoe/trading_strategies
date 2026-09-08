"""Shared risk floors applied to backtest evidence.

One threshold, applied at two independent stages of the research pipeline, so the
two gates cannot silently drift apart:

- optimizer candidate eligibility (``backtesting/domain/optimization.py``) rejects a
  training candidate whose drawdown breaches the floor, so it can never be selected;
- the promotion research gate (``domain/promotion/policy.py``) seeds its
  operator-tunable default from the same value.

The promotion side stays overridable per operator settings while the optimizer's is
a hard code gate — deliberately, since a selection rule an operator can relax is a
selection rule that stops meaning anything. Sharing the constant keeps the *default*
answer to "how much drawdown is too much" in one place.
"""

from __future__ import annotations

# Worst peak-to-trough decline tolerated from backtest evidence, as a negative
# percentage (a 25% decline is -25.0). Values below this are rejected.
MAX_ACCEPTABLE_DRAWDOWN_PCT = -25.0
