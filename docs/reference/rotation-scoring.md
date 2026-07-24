# Rotation Scoring — components, data sources, and deferred work

Type: notes
Status: Active
Created: 2026-07-24
Last Reviewed: 2026-07-24
Purpose: What each term in the champion/challenger rotation score means, where its value comes from, and what the two deferred components (`cost_penalty`, `regime_fit`) would need to become real.
Related: [Backtesting](backtesting.md), [Strategies](strategies.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Purpose

Read this before touching rotation scoring, or when deciding whether to build out
`regime_fit`. It records what the score measures, which components have an honest
data source, and — for the two that do not — exactly what is missing and what a
real implementation would need.

## The score

`evaluate_champion_challenger_rotation` (`src/trading/domain/rotation/policy.py`)
scores each strategy as:

```text
score = risk_adjusted_return
      + stability
      - drawdown_penalty
      - cost_penalty
      + regime_fit
```

Every term is expressed in **percentage points**, the same unit as the blended
evaluation score that feeds `risk_adjusted_return`. Keeping one unit is what makes
the operator-tunable weights (`RotationScoreWeights`, defaults 1.0 / 0.25 / 0.20 /
0.10 / 0.10) meaningful — a component on a different scale would silently dominate.

The score only decides the **score-superiority gate**. The rotation also requires a
cooldown gate, a minimum-sample gate, and an outperformance gate (which compares
`risk_adjusted_return` alone). So the components sharpen a close call between
similar-return strategies; they cannot force a rotation on their own.

| Component | Status | Source |
|---|---|---|
| `risk_adjusted_return` | Live | Blended evaluation decision score (`derive_decision_score`) |
| `stability` | Live | Negative spread of walk-forward window returns |
| `drawdown_penalty` | Live | Magnitude of backtest `max_drawdown_pct` |
| `cost_penalty` | **Inert (0.0)** | None — see below |
| `regime_fit` | **Inert (0.0)** | None — see below |

The live derivations are in `src/trading/domain/rotation/score_components.py`; the
metric build is `src/trading/services/books/rotation/metrics.py`.

Both inert components are **no longer operator-settable** — their weights were
removed from the CLI and the settable field list (`ROTATION_POLICY_FIELDS`) so
nobody tunes a dial that does nothing. Their columns remain on
`book_rotation_settings` and are preserved across edits.

## `cost_penalty` — why it stays zero

A turnover/trading-cost penalty would double-count. The backtest simulation already
deducts per-trade fees (`pnl = (price - avg_cost) * qty - fee`), so
`total_return_pct` — and therefore both `risk_adjusted_return` and
`drawdown_penalty` — are already net of modeled cost. A separate penalty would only
be non-redundant if it captured a cost the flat fee does not: slippage, market
impact, bid/ask spread, or a deliberate bias toward low-turnover strategies. Even
then, the natural home is the backtest cost model, not a rotation weight.
**Recommendation: leave inert unless the fee model gains un-modeled cost dimensions.**

## `regime_fit` — what it would track and what it needs

`regime_fit` would reward the strategy suited to the **current market regime**
(risk-on / neutral / risk-off), so rotation prefers, say, a momentum strategy in a
risk-on tape and a defensive one when the tape turns risk-off — beyond what trailing
return already captures.

### What we learned (the useful part)

**A regime signal already exists in the codebase.** It is not greenfield.
`src/infrastructure/feature_providers/policy_provider.py` computes
`policy_risk_on_score ∈ [0, 1]` — a sigmoid of SPY's trailing return versus a basket
of defensive ETFs (TLT, GLD, XLU, UUP). With the existing thresholds
`POLICY_RISK_ON_BUY_THRESHOLD = 0.55` and `POLICY_RISK_OFF_SELL_THRESHOLD = 0.45`
(`src/trading/domain/feature_provider.py`), that score is already a three-state
classifier:

```text
score > 0.55  -> risk-on
0.45–0.55     -> neutral
score < 0.45  -> risk-off
```

It is market-wide and cached (returned regardless of the queried ticker), and today
it is wired only into **strategy signal generation** (`fetch_policy` in
`services/execution/selection/selection.py`), consumed by the `policy_regime` and
`macro_proxy_regime` strategies. Rotation never reads it.

**The original design existed and was deliberately torn out.** Migration `0014`
dropped the `regime_strategy_risk_on_id` / `_neutral_id` / `_risk_off_id` columns
from `book_rotation_settings` as dead — the per-book "which strategy for which
regime" mapping. Their weight (`regime_fit_weight`) was kept. So the current state is
"detector exists, mapping removed, weight stranded."

### What a real implementation needs

Three pieces, none of which exist wired to rotation:

1. **Current-regime read at decision time.** Surface `policy_risk_on_score` (or a
   dedicated regime classifier) to the rotation path and bucket it into
   risk-on/neutral/risk-off using the thresholds above.
2. **Per-strategy regime affinity — the real design decision.** Which regime does a
   strategy suit? Options, roughly in increasing effort:
   - *Explicit mapping* (what `0014` removed): re-add per-book regime→strategy
     columns and let the operator declare affinity. Simple, but it is configuration,
     not evidence.
   - *Family-derived*: infer affinity from the strategy primitive/family (momentum →
     risk-on, mean-reversion/defensive → risk-off). Cheap, coarse, no new storage.
   - *Evidence-derived*: score each strategy's historical returns **conditioned on
     the regime that was active** in each window, so affinity comes from measured
     behavior. Most honest, most work — needs regime labels joined to evaluation
     windows.
3. **A percentage-point contribution.** `regime_fit` must be on the same scale as the
   other components (e.g. `+affinity_bonus_pct` when the strategy's affinity matches
   the current regime, tapering through neutral), so the existing weight stays
   meaningful.

### Methodology caveats (read before building)

- **Point-in-time correctness.** Backtests and replays must use the regime that was
  active *as of each historical date*, not today's. `policy_provider` fetches a
  live trailing window, so it is only valid for a live "now" decision. A historical
  regime series would have to be reconstructed from as-of ETF data — otherwise
  `regime_fit` injects look-ahead bias, which the evaluation-honesty rules forbid.
- **Live-data dependency in the decision path.** Reading a market regime at rotation
  time makes the decision depend on a live network fetch (yfinance). Rotation is
  currently evidence-only (it reads the stored evaluation artifact). Adding a live
  dependency needs a caching/failure story — a stale or unavailable regime must
  degrade to neutral (`0.0`), never block or bias the rotation.
- **Evidence-derived affinity is circular if naive.** Conditioning a strategy's
  score on regime and then using it to pick strategies per regime can overfit thin
  per-regime samples. Any evidence-derived path needs the same minimum-sample
  discipline the rotation gates already apply.

### Suggested minimal first step (if pursued)

The lowest-risk slice that produces real signal: **family-derived affinity + live
regime, neutral-safe.** Bucket the current `policy_risk_on_score`, map each
strategy's primitive to a coarse risk-on/neutral/risk-off affinity, and award a
small fixed percentage-point bonus on a match (zero on mismatch or when the regime
is unavailable). It avoids new schema and the point-in-time problem for *live*
rotation, while proving whether regime awareness changes decisions at all before
investing in an evidence-derived version. It does **not** make backtest/replay
regime-aware — that needs the historical regime series above.

## Where the plumbing lives

- Metric build (leaves the two inert): `src/trading/services/books/rotation/metrics.py`
- Pure derivations: `src/trading/domain/rotation/score_components.py`
- Score arithmetic: `src/trading/domain/rotation/policy.py`
- Weights + resolution: `src/trading/services/books/rotation/engine.py`
- Operator-settable fields: `ROTATION_POLICY_FIELDS` in `src/trading/services/parameters/mutations.py`
- Existing regime signal: `src/infrastructure/feature_providers/policy_provider.py`
