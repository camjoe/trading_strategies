# Strategy Catalog Reference

Type: notes
Status: Active
Created: 2026-03-11
Last Reviewed: 2026-07-21
Purpose: Catalog of strategy signal families, compatibility behavior, and evaluation workflow.
Related: [Backtesting](backtesting.md), [Sentiment Signals](sentiment-signals.md), [Trading Package Map](../maps/trading-package-map.md)

## Purpose

Provide the current strategy catalog, compatibility behavior, and evaluation
checklist for research/backtesting flows.

## Canonical Source

A strategy is a **code primitive plus data knobs**, split across two sources:

- **Signal primitives (code)** — `src/trading/domain/strategy_signals.py`
  (`PRIMITIVE_CATALOG`): the tested signal functions and their knob schemas. Adding genuinely new
  signal *logic* is still a code change. `STRATEGY_REGISTRY` seeds the primitive catalog and remains
  the alias-compat source for legacy labels.
- **Strategy definitions (data)** — the `strategies` catalog table: each row binds a primitive to a
  concrete `params_json`, plus an operator `description`, status (`draft`/`frozen`/`retired`), and
  `enabled`. Primitive-owned metadata (style, required features, knob schema) is **not** stored on the
  row — it is derived from the code `PrimitiveSpec` at resolve time (revision `0017`).

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
- `macd`
- `breakout`
- `pullback_trend`
- `ma_crossover`
- `volatility_filtered_trend`

### Mean-reversion family

- `mean_reversion`
- `rsi`
- `bollinger_mean_reversion`

### Proxy-feature family (price-derived features)

- `topic_proxy_rotation`
- `macro_proxy_regime`

### Alternative-data family (external providers)

- `policy_regime`
- `news_sentiment`
- `social_trend_rotation`

## Strategy Resolution Behavior

At runtime a book's assigned `strategy_key` resolves through the catalog row's `primitive`
(`resolve_catalog_strategy` → `resolve_primitive`), so data variants run the correct signal function.

Label compatibility for legacy/alias inputs is still handled by `resolve_strategy(...)` in
`src/trading/domain/strategy_signals.py` (used by the catalog resolver's alias fallback, the label
bridge, and backtesting).

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
- `topic_rotation` / `theme_proxy` -> `topic_proxy_rotation`
- `policy_etf` / `political_regime` -> `policy_regime`

Backtest and walk-forward reports use the catalog `strategy_key` as the canonical display key. Older
aliases such as `trend_v1` are compatibility inputs, not canonical evidence keys.

## Data and Dependency Notes

Price-based and proxy-feature strategies:

- depend on configured market-data provider (default `yfinance`)
- run on daily-bar assumptions in current backtesting/runtime flows

Alternative-data strategies:

- depend on `src/infrastructure/feature_providers/` providers
- use `ExternalFeatureBundle` inputs and degrade conservatively when data is unavailable
- runtime deps in `requirements-base.txt` include:
  - `praw`
  - `pytrends`
  - `vaderSentiment`
  - optional `newsapi-python`

Credential notes (alternative-data paths):

- `NEWS_API_KEY` (optional for NewsAPI supplementation)
- `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (required for Reddit component)

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

The current strategy catalog, generic signal primitives, research candidates, and roadmap are
intentionally public. Honest known gaps remain public unless a concrete security, privacy, ownership,
or proprietary-information concern requires otherwise.

Classify every new strategy primitive, feature provider, parameter set, fixture, result, and related
documentation before placing it in tracked files:

- **Public example:** safe to publish permanently and appropriate for tracked source, tests, and docs.
- **Private/proprietary:** keep research and parameters under `local/strategies/`. Put executable logic
  that must integrate with the application in a separately distributed private package or repository
  behind the established strategy interfaces.

Do not copy private strategy names, thresholds, hypotheses, evaluation results, or fixtures into
tracked tests or documentation. If classification is uncertain, treat the material as private until
the owner makes an explicit publication decision. Removing it in a later commit does not retract
copies from public Git history.

## Research Candidates (Not Implemented as First-Class Strategies)

- pairs/statistical arbitrage
- broader multi-factor framework
- richer cross-sectional momentum ranking engine

## Related References

- `docs/reference/backtesting.md`
- `docs/reference/sentiment-signals.md`
- `src/trading/backtesting/README.md`
