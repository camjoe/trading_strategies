# Rotation Scoring — components and data sources

Type: notes
Status: Active
Created: 2026-07-24
Last Reviewed: 2026-07-26
Purpose: What each term in the champion/challenger rotation score means, where its value comes from, and the as-built `regime_fit` design.
Related: [Backtesting](backtesting.md), [Strategies](strategies.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Purpose

Read this before touching rotation scoring. It records what the score measures,
which components have an honest data source, and the as-built family-derived +
live-regime design behind `regime_fit`.

## The score

`evaluate_champion_challenger_rotation` (`src/trading/domain/rotation/policy.py`)
scores each strategy as:

```text
score = risk_adjusted_return
      + stability
      - drawdown_penalty
      + regime_fit
```

Every term is expressed in **percentage points**, the same unit as the blended
evaluation score that feeds `risk_adjusted_return`. Keeping one unit is what makes
the operator-tunable weights (`RotationScoreWeights`, defaults 1.0 / 0.25 / 0.20 /
0.10) meaningful — a component on a different scale would silently dominate.

The score only decides the **score-superiority gate**. The rotation also requires a
cooldown gate, a minimum-sample gate, and an outperformance gate (which compares
`risk_adjusted_return` alone). So the components sharpen a close call between
similar-return strategies; they cannot force a rotation on their own.

| Component | Status | Source |
|---|---|---|
| `risk_adjusted_return` | Live | Blended evaluation decision score (`derive_decision_score`) |
| `stability` | Live | Negative standard deviation of walk-forward window returns |
| `drawdown_penalty` | Live | Magnitude of backtest `max_drawdown_pct` |
| `regime_fit` | **Live (2026-07-26)** | Family-derived affinity vs. a live ETF regime read — see below |

The live derivations are in `src/trading/domain/rotation/score_components.py`; the
metric build is `src/trading/services/books/rotation/metrics.py`.

A fifth component, `cost_penalty`, existed as an always-zero placeholder (revision
`0014` onward) and was removed (revision `0026`) rather than kept reserved: a
turnover/trading-cost penalty would have double-counted, since backtest returns are
already net of modeled per-trade fees, and no un-modeled cost dimension was ever
identified to justify keeping the slot. If one is identified later (slippage beyond
the modeled fee, market impact, bid/ask spread), the natural home is the backtest
cost model, and a rotation weight can be re-added against a real metric at that
point.

## `regime_fit` — as-built (2026-07-26)

`regime_fit` rewards the strategy suited to the **current market regime**
(risk-on / neutral / risk-off), so rotation prefers, say, a `trend` strategy in a
risk-on tape and a `mean_reversion` one when the tape turns risk-off — beyond what
trailing return already captures.

### The regime signal

`src/infrastructure/feature_providers/policy_provider.py` computes
`policy_risk_on_score ∈ [0, 1]` — a sigmoid of SPY's trailing return versus a basket
of defensive ETFs (TLT, GLD, XLU, UUP). It is market-wide and cached (returned
regardless of the queried ticker). Rotation reads it via
`FeatureFetcherSet.fetch_policy`, the same callable the strategy signal path uses
when a feature-gated strategy is registered, so "risk-on" means the same thing in
both places.
`regime_bucket_from_risk_on_score` (`domain/rotation/score_components.py`) buckets
it using the same thresholds the signal layer uses
(`POLICY_RISK_ON_BUY_THRESHOLD = 0.55` / `POLICY_RISK_OFF_SELL_THRESHOLD = 0.45`,
`src/trading/domain/feature_provider.py`).

### Per-strategy affinity — family-derived

Migration `0014` had dropped the `regime_strategy_risk_on_id` / `_neutral_id` /
`_risk_off_id` columns from `book_rotation_settings` as dead — the per-book
"which strategy for which regime" explicit mapping — while keeping the
`regime_fit_weight` column. Rather than resurrecting that mapping (configuration,
not evidence) or building an evidence-derived affinity (conditioning historical
returns on regime — the most honest option, but needing regime labels joined to
evaluation windows and the same minimum-sample discipline the rotation gates
already apply), the as-built design uses the cheapest defensible option:
**family-derived affinity** from the strategy's primitive style
(`_STYLE_AFFINITY` in `score_components.py`): `trend` → risk-on, `mean_reversion` →
risk-off. Everything else (`neutral`, `alternative`) gets no bonus in any regime —
a strategy that already reacts to regime in its own signal logic would otherwise
be counted twice.
Evidence-derived affinity and the explicit per-book mapping remain open, larger,
follow-on options if family-derived proves too coarse.

### The contribution

`regime_fit_from_style` (`score_components.py`) returns `REGIME_FIT_MATCH_BONUS_PCT`
(2.0 percentage points) on a match, and `NEUTRAL_COMPONENT` (0.0) otherwise —
mismatch, neutral regime, unmapped style, or an unavailable regime read all get the
same neutral value. **Never a penalty** — a strategy is only ever optionally
rewarded for a plausible match, never punished for its style. At the default
`regime_fit_weight` (0.10) a match contributes ~0.2pp to the final weighted score.

### Methodology notes (still apply)

- **Live-rotation-only, not backtest/replay-aware.** `policy_provider` fetches a
  live trailing window, valid only for a live "now" decision. Backtests and
  walk-forward runs do **not** call `fetch_regime` (nothing was wired into
  `backtesting/`), so this does not inject look-ahead bias into evaluation — but it
  also means `regime_fit` cannot yet be reproduced by a historical replay. Making
  backtests regime-aware needs a reconstructed as-of regime series, which is a
  separate, larger piece of work.
- **Neutral-safe by construction.** `fetch_regime` failures/unavailability
  (`ExternalFeatureBundle.unavailable()`, caught inside
  `ExternalFeatureProvider.get_features` — never raises) flow through as
  `bundle.get(POLICY_RISK_ON_SCORE) is None` → `regime_bucket_from_risk_on_score`
  returns `None` → `regime_fit_from_style` returns `NEUTRAL_COMPONENT`. A stale or
  unreachable regime read degrades quietly; it never blocks or biases rotation.
- **Evidence-derived affinity, if built later, is circular if naive.** Conditioning
  a strategy's score on regime and then using it to pick strategies per regime can
  overfit thin per-regime samples — apply the same minimum-sample discipline the
  rotation gates already use.

## Where the plumbing lives

- Metric build (computes `regime_fit` when `fetch_regime` is given): `src/trading/services/books/rotation/metrics.py`
- Pure derivations (`MarketRegime`, `regime_bucket_from_risk_on_score`,
  `regime_fit_from_style`, `_STYLE_AFFINITY`): `src/trading/domain/rotation/score_components.py`
- Score arithmetic: `src/trading/domain/rotation/policy.py`
- Weights + resolution: `src/trading/services/books/rotation/engine.py`
- Operator-settable fields: `ROTATION_POLICY_FIELDS` in `src/trading/services/parameters/mutations.py`
- `fetch_regime` threading (live rotation): `challenger_evaluation.py` →
  `account_rotation.py` → `services/auto_trading/runtime.py` (from the
  `FeatureFetcherSet` the composition root — `run_auto_trades.py` — already builds)
- `fetch_regime` threading (shadow eval): `interfaces/runtime/jobs/daily/challenger_shadow_eval.py`
  (its own module-level `PolicyFeatureProvider`, for output parity with real rotation)
- Regime signal: `src/infrastructure/feature_providers/policy_provider.py`
