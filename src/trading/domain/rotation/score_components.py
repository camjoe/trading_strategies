"""Pure derivations for the rotation score's risk components.

``evaluate_champion_challenger_rotation`` scores a strategy as::

    risk_adjusted_return + stability - drawdown_penalty - cost_penalty + regime_fit

Every term is expressed in **percentage points**, the same unit as the blended
evaluation score that feeds ``risk_adjusted_return`` (itself derived from
``total_return_pct`` / ``return_pct``). Keeping one unit is what makes the
operator-tunable weights meaningful — a component on a different scale would
silently dominate the sum.

Sign conventions matter here:

- ``stability`` is **added**, so a larger value must mean steadier.
- ``drawdown_penalty`` is **subtracted**, so it must be a positive magnitude.
  ``max_drawdown_pct`` is stored as a negative number, so it is converted.
"""

from __future__ import annotations

# Component value that neither rewards nor penalizes a strategy. Used whenever the
# supporting evidence is missing, so an absent input can never look like a good score.
NEUTRAL_COMPONENT = 0.0

# A single out-of-sample window has zero spread, which would read as perfect
# steadiness. Require at least two windows before claiming to measure stability.
MIN_WINDOWS_FOR_STABILITY = 2


def stability_from_window_returns(
    *,
    best_return_pct: float | None,
    worst_return_pct: float | None,
    window_count: int,
) -> float:
    """Negative spread of out-of-sample window returns; closer to zero is steadier.

    Measures *consistency* across the walk-forward windows: a strategy whose
    window returns cluster tightly scores near ``0.0``, while a strategy that
    swings between good and bad windows scores further negative.

    This is a **range**, not a standard deviation — the evaluation artifact
    persists only best/worst/average/median per group, so the range is the only
    dispersion statistic available without re-reading every window run. It
    therefore treats upside and downside spread alike; a strategy that is
    inconsistently *good* is still scored as less steady.
    """
    if window_count < MIN_WINDOWS_FOR_STABILITY:
        return NEUTRAL_COMPONENT
    if best_return_pct is None or worst_return_pct is None:
        return NEUTRAL_COMPONENT
    spread = float(best_return_pct) - float(worst_return_pct)
    return -max(0.0, spread)


def drawdown_penalty_from_max_drawdown(max_drawdown_pct: float | None) -> float:
    """Positive magnitude of the worst peak-to-trough decline.

    ``max_drawdown_pct`` is produced as a negative percentage (a 12% decline is
    ``-12.0``), while the policy *subtracts* this component. Returning the
    magnitude is what makes a deeper drawdown lower the score rather than raise
    it.
    """
    if max_drawdown_pct is None:
        return NEUTRAL_COMPONENT
    return abs(float(max_drawdown_pct))
