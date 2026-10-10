# ADR: Rotation score components, with family-derived regime fit

Type: adr
Status: Accepted
Created: 2026-08-02
Last Reviewed: 2026-08-02
Purpose: Record what each term in the champion/challenger rotation score measures, why every term is expressed in percentage points, and why `regime_fit` derives its per-strategy affinity from primitive style rather than from configuration or from evidence.
Related: [ADR 016: Optimizer Experiments as Research Evidence](016-optimizer-experiments-as-research-evidence.md), [ADR 010: Book-Keyed Execution Model](010-book-keyed-execution-model.md), [Backtesting](../reference/backtesting.md), [Strategies](../reference/strategies.md)

## Context

`evaluate_champion_challenger_rotation` (`src/trading/domain/rotation/policy.py`) scores each
strategy as:

```text
score = risk_adjusted_return
      + stability
      - drawdown_penalty
      + regime_fit
```

Two constraints shaped the components.

**Units have to match.** Every term is expressed in percentage points, the same unit as the
blended evaluation score feeding `risk_adjusted_return`. That is what makes the
operator-tunable weights (`RotationScoreWeights`, defaults 1.0 / 0.25 / 0.20 / 0.10)
meaningful — a component on a different scale would silently dominate regardless of its
weight.

**The score is not the whole gate.** It decides only the score-superiority check. Rotation
also requires a cooldown gate, a minimum-sample gate, and an outperformance gate (which
compares `risk_adjusted_return` alone). The components sharpen a close call between
similar-return strategies; they cannot force a rotation on their own.

`regime_fit` was the open one. Revision `0014` had dropped the
`regime_strategy_risk_on_id` / `_neutral_id` / `_risk_off_id` columns from
`book_rotation_settings` as dead — the per-book "which strategy for which regime" explicit
mapping — while keeping the `regime_fit_weight` column. So the weight existed with nothing
behind it.

Alternatives considered for per-strategy affinity:

- **Resurrect the explicit per-book mapping.** Rejected: that is configuration, not
  evidence. An operator asserting which strategy suits which regime records an opinion the
  rotation then treats as a measurement.
- **Evidence-derived affinity** — condition historical returns on regime. The most honest
  option, and rejected only on cost: it needs regime labels joined to evaluation windows and
  the same minimum-sample discipline the rotation gates already apply. It remains the
  natural successor if family-derived proves too coarse.

## Decision

The four components and their sources:

| Component | Source |
|---|---|
| `risk_adjusted_return` | Blended evaluation decision score (`derive_decision_score`) |
| `stability` | Consistency across walk-forward windows (`stability_from_window_returns`) |
| `drawdown_penalty` | Magnitude of backtest `max_drawdown_pct` |
| `regime_fit` | Family-derived affinity vs. a live ETF regime read |

**`regime_fit` uses family-derived affinity** — the cheapest defensible option of the three.
`_STYLE_AFFINITY` (`domain/rotation/score_components.py`) maps the strategy's primitive
style: `trend` → risk-on, `mean_reversion` → risk-off. Everything else (`neutral`,
`alternative`) gets no bonus in any regime, because a strategy that already reacts to regime
in its own signal logic would otherwise be counted twice.

**The regime read is shared with the signal layer.**
`src/infrastructure/feature_providers/policy_provider.py` computes
`policy_risk_on_score ∈ [0, 1]`, a sigmoid of SPY's trailing return against a basket of
defensive ETFs (TLT, GLD, XLU, UUP). It is market-wide and cached. Rotation reads it through
`FeatureFetcherSet.fetch_policy` — the same callable the strategy signal path uses — and
`regime_bucket_from_risk_on_score` buckets it on the same thresholds the signal layer uses
(`POLICY_RISK_ON_BUY_THRESHOLD = 0.55` / `POLICY_RISK_OFF_SELL_THRESHOLD = 0.45`). "Risk-on"
therefore means the same thing in both places.

**A match is rewarded, a mismatch is never punished.** `regime_fit_from_style` returns
`REGIME_FIT_MATCH_BONUS_PCT` (2.0 percentage points) on a match and `NEUTRAL_COMPONENT`
(0.0) otherwise — mismatch, neutral regime, unmapped style, and an unavailable regime read
all collapse to the same neutral value. At the default `regime_fit_weight` (0.10) a match
contributes about 0.2pp to the final weighted score.

A fifth component, `cost_penalty`, was an always-zero placeholder removed in revision `0026`;
that revision's docstring holds the reasoning and, being an applied migration, cannot drift.
Rotation-specific addendum: if an un-modeled cost dimension is identified later (slippage
beyond the modeled fee, market impact, bid/ask spread), the natural home is the backtest cost
model, and a rotation weight can be re-added against a real metric at that point.

## Consequences

**Live-rotation-only, not backtest- or replay-aware.** `policy_provider` fetches a live
trailing window, valid only for a live "now" decision. Backtests and walk-forward runs do not
call `fetch_regime` — nothing was wired into `backtesting/` — so this injects no look-ahead
bias into evaluation. The price is that `regime_fit` cannot be reproduced by a historical
replay. Making backtests regime-aware needs a reconstructed as-of regime series, which is
separate, larger work.

**Neutral-safe by construction.** A `fetch_regime` failure returns
`ExternalFeatureBundle.unavailable()` (caught inside `ExternalFeatureProvider.get_features`,
which never raises), so `bundle.get(POLICY_RISK_ON_SCORE)` is `None`,
`regime_bucket_from_risk_on_score` returns `None`, and `regime_fit_from_style` returns
`NEUTRAL_COMPONENT`. A stale or unreachable regime read degrades quietly; it never blocks or
biases rotation.

**Family-derived affinity is coarse by design.** Two strategies of the same primitive style
score identically on this term no matter how differently they have behaved in past regimes.
That is the accepted cost of not building the evidence-derived version.

**Evidence-derived affinity is circular if built naively.** Conditioning a strategy's score
on regime and then using that score to pick strategies per regime can overfit thin
per-regime samples. Whoever builds it must apply the same minimum-sample discipline the
rotation gates already use.
