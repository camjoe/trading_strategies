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

from enum import StrEnum

from trading.domain.feature_provider import POLICY_RISK_OFF_SELL_THRESHOLD, POLICY_RISK_ON_BUY_THRESHOLD

# Component value that neither rewards nor penalizes a strategy. Used whenever the
# supporting evidence is missing, so an absent input can never look like a good score.
NEUTRAL_COMPONENT = 0.0

# A single out-of-sample window has zero spread, which would read as perfect
# steadiness. Require at least two windows before claiming to measure stability.
MIN_WINDOWS_FOR_STABILITY = 2


class MarketRegime(StrEnum):
    """A coarse market-regime bucket, and a strategy family's affinity to one.

    The same three-value vocabulary serves both roles: "the market is currently
    risk-on" and "this strategy family does well in risk-on" are compared for
    equality by ``regime_fit_from_style``.
    """

    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


def regime_bucket_from_risk_on_score(risk_on_score: float | None) -> MarketRegime | None:
    """Bucket a live ``policy_risk_on_score`` into risk-on/neutral/risk-off.

    Uses the same thresholds the ``policy_regime``/``macro_proxy_regime`` strategy
    signals already treat as risk-on/risk-off, so "the market is risk-on" means the
    same thing here as it does there. Returns ``None`` when the score itself is
    unavailable (a failed or stale live fetch) — the caller must treat that the same
    as a non-matching regime, never as a reason to block or bias the decision.
    """
    if risk_on_score is None:
        return None
    if risk_on_score > POLICY_RISK_ON_BUY_THRESHOLD:
        return MarketRegime.RISK_ON
    if risk_on_score < POLICY_RISK_OFF_SELL_THRESHOLD:
        return MarketRegime.RISK_OFF
    return MarketRegime.NEUTRAL


# Coarse strategy-family -> regime affinity (the "family-derived" design from
# docs/reference/rotation-scoring.md, not per-strategy evidence). Styles not listed
# here — "neutral", and "alternative" (policy_regime, macro_proxy_regime, ... —
# strategies that already react to regime in their own signal logic, so giving them
# an affinity here too would double up) — default to no bonus in any regime.
_STYLE_AFFINITY: dict[str, MarketRegime] = {
    "trend": MarketRegime.RISK_ON,
    "mean_reversion": MarketRegime.RISK_OFF,
}

# Small fixed percentage-point bonus for a family/regime match. Same unit as the
# other components; at the default regime_fit_weight (0.10) this contributes ~0.2pp
# to the final weighted score — real but modest next to stability/drawdown_penalty.
REGIME_FIT_MATCH_BONUS_PCT = 2.0


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


def regime_fit_from_style(*, strategy_style: str | None, current_regime: MarketRegime | None) -> float:
    """Small bonus when a strategy family's affinity matches the live regime.

    Neutral-safe by construction: an unavailable regime, a neutral regime, an
    unmapped style, or a mismatch all return ``NEUTRAL_COMPONENT`` — never a
    penalty. A strategy is never punished for its style, only optionally rewarded
    for a plausible match. This is the "minimal first step" from
    ``docs/reference/rotation-scoring.md``: family-derived affinity against a live
    regime read, not evidence-derived or an explicit per-book mapping.
    """
    if current_regime is None or current_regime == MarketRegime.NEUTRAL:
        return NEUTRAL_COMPONENT
    affinity = _STYLE_AFFINITY.get(strategy_style or "")
    if affinity is None or affinity != current_regime:
        return NEUTRAL_COMPONENT
    return REGIME_FIT_MATCH_BONUS_PCT
