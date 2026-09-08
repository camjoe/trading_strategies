# Strategy Catalog Reference

Type: notes
Status: Active
Created: 2026-03-11
Last Reviewed: 2026-08-02
Purpose: Catalog of strategy signal families, compatibility behavior, and evaluation workflow.
Related: [Backtesting](backtesting.md), [Sentiment Signals](sentiment-signals.md), [Trading Package Map](../maps/trading-package-map.md)

## Canonical Source

A strategy is a **code primitive plus data knobs**, split across two sources:

- **Signal primitives (code)** — `src/trading/domain/strategies/` (`registry.PRIMITIVE_CATALOG`,
  signal functions in `signals/`): the tested signal functions and their knob schemas. Adding genuinely new
  signal *logic* is still a code change. `STRATEGY_REGISTRY` seeds the primitive catalog and remains
  the alias-compat source for legacy labels.
- **Strategy definitions (data)** — the `strategies` catalog table: each row binds a primitive to a
  concrete `params_json`, plus an operator `description`, status (`draft`/`frozen`/`retired`), and
  `enabled`. Primitive-owned metadata (style, required features, knob schema) is **not** stored on the
  row — it is derived from the code `PrimitiveSpec` at resolve time.

**A primitive needs tunable knobs.** A primitive whose `default_params` is empty gives the
walk-forward optimizer nothing to search, so it can never enter the optimize→promote loop — `macd`
was retired for exactly that reason. Declare the knobs a signal actually reads.

**The `strategies` catalog is canonical at runtime**: a book's assignment names a `strategies` row, and
`resolve_catalog_strategy` (`trading.services.strategy_catalog.resolution`) resolves it to the
primitive's signal function plus the effective knobs (the primitive's defaults with the row's
`params_json` layered on top). A *variant* — a new `strategy_key` on the same primitive with tuned
knobs — is therefore a pure data change, no deploy.

Operators edit the catalog through the CLI (`trading.services.strategy_catalog.mutations`):

- `create-strategy-variant --strategy <key> --primitive <p> --set knob=value …` — a new draft row.
- `configure-strategy --strategy <key> --set knob=value … [--enabled true|false]` — edit a draft's
  knobs (merged over the existing ones); knob overrides are validated against the primitive schema.
- `freeze-strategy --strategy <key>` — freeze a strategy once it has evidence or live usage; tuning a
  frozen row then requires a new variant.

## Strategy Families

### Trend family

- `trend`
- `breakout`
- `pullback_trend`
- `ma_crossover`
- `volatility_filtered_trend`

### Mean-reversion family

- `mean_reversion`
- `rsi`
- `bollinger_mean_reversion`

### Retired

`macd` and the five feature-gated primitives were removed from the registry; their rules and
thresholds are in [Retired Strategy Primitives](retired-strategy-primitives.md) so any can be
rebuilt. The feature-provider infrastructure behind the feature-gated ones was kept but is dormant —
no strategy in the catalog declares `required_features`. See
[Sentiment Signals](sentiment-signals.md) for the provider boundary and what a consuming strategy
would have to declare.

## Strategy Resolution Behavior

At runtime a book's assigned `strategy_key` resolves through the catalog row's `primitive`
(`resolve_catalog_strategy` → `resolve_primitive`), so data variants run the correct signal function.

Label compatibility for legacy/alias inputs is still handled by `resolve_strategy(...)` in
`src/trading/domain/strategies/resolution.py` (used by the catalog resolver's alias fallback, the
label bridge, and backtesting).

Order of resolution:

1. exact strategy id
2. registered aliases
3. keyword compatibility matching

Unknown labels raise `ValidationError` (a `ValueError` subclass; they do not
silently fall back). In the web UI this maps to HTTP 400 — see
`docs/adr/007-ui-error-mapping.md`.

Examples of compatibility labels that still resolve:

- trend/momentum variants -> `trend`
- mean-reversion variants -> `mean_reversion`
- `donchian_push` -> `breakout`
- `vol_filter_trend` -> `volatility_filtered_trend`

Backtest and walk-forward reports use the catalog `strategy_key` as the canonical display key. Older
aliases such as `trend_v1` are compatibility inputs, not canonical evidence keys.

## Data and Dependency Notes

Every strategy in the catalog is price-based: each depends on the configured market-data provider
(default `yfinance`) and runs on daily-bar assumptions in current backtesting and runtime flows.

The alternative-data path — providers, packages, and credentials — is documented in
[Sentiment Signals](sentiment-signals.md). Nothing in the catalog uses it today.

## Evaluation Checklist

Use this checklist when proposing new strategies:

- publication classification: intentionally public example or private/proprietary
- strategy hypothesis and intended market regime
- required data sources and fallback behavior
- entry/exit rules and position sizing
- transaction-cost and slippage assumptions
- risk limits and failure modes
- validation plan (walk-forward/out-of-sample)
- comparable baseline(s)
- reporting metrics (return, drawdown, turnover, hit rate, etc.)

## Publication Boundary

The current strategy catalog and generic signal primitives are intentionally public, as are honest
known gaps. The classification rule for anything new — primitives, parameters, fixtures, results,
docs — is in [AGENTS.md](../../AGENTS.md) core rules.

The reason it is a pre-commit decision rather than a cleanup task: removing private material in a
later commit does not retract it from public Git history.

## Related References

- `docs/reference/backtesting.md`
- `docs/reference/sentiment-signals.md`
- `src/backtesting/README.md`
