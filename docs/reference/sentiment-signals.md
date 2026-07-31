# Sentiment and Alternative Signal Reference

Type: notes
Status: Active
Created: 2026-03-30
Last Reviewed: 2026-07-31
Purpose: Describe the external feature-provider architecture that supplies news, social and policy data to strategies, and the contract a strategy must meet to consume it.
Related: [Strategy Catalog](strategies.md), [Retired Strategy Primitives](retired-strategy-primitives.md), [Trading Package Map](../maps/trading-package-map.md)

> **No strategy consumes these providers today.** The three that did
> (`policy_regime`, `news_sentiment`, `social_trend_rotation`) were retired; their rules are in
> [Retired Strategy Primitives](retired-strategy-primitives.md). The provider infrastructure below
> is intact and supported — this document describes what a strategy would plug into.

## Provider boundary

`src/trading/domain/feature_provider.py` defines `ExternalFeatureProvider` and
`ExternalFeatureBundle`. Concrete providers own their third-party SDK imports and network calls, and
live only in `src/infrastructure/feature_providers/`:

| Provider | Feature source |
|---|---|
| `policy_provider.py` | ETF proxy returns such as TLT/GLD/XLU/UUP vs SPY |
| `news_provider.py` | RSS headlines plus optional NewsAPI supplementation, scored with VADER |
| `social_provider.py` | Google Trends interest plus Reddit mention/sentiment data |

`ProxyFeatureDataProvider` (`src/trading/services/market_data/features.py`) is separate: it derives
sector and macro proxy features from market data alone, with no external API.

## What a consuming strategy must do

1. Declare its feature keys in `required_features` on its `StrategySpec`. The engine only builds a
   feature bundle when a strategy declares them.
2. Set `strategy_style="alternative"`, which is what `build_feature_history_fn`
   (`services/execution/selection/selection.py`) routes on to pick a fetcher in the live path.
3. Read features from the last row of the frame it is handed, and return `"hold"` when any required
   value is missing — see the degradation contract below.

## Degradation contract

Enforced by convention and by the architecture rules in
`docs/architecture/architecture-conventions.md`:

- Every `_fetch()` catches all exceptions and returns `ExternalFeatureBundle(available=False, ...)`.
  A provider outage must never fail a trading run.
- Signal functions check availability first and return `"hold"` when data is missing. A feature value
  that is absent, NaN or infinite counts as missing — decisions are never made on unbounded inputs.
- Credentials come from the environment, never from source. `secret_hygiene_check` enforces this.

## Operator visibility

The `alt-strategies` UI tab shows each provider's status and current feature values, served by
`apps/paper_trading_web/backend/services/features/`. Its signal column reads `hold` for every row,
because no strategy consumes the features; restoring one makes it meaningful again.

## Related References

- `docs/reference/strategies.md`
- `docs/reference/retired-strategy-primitives.md`
- `docs/architecture/architecture-conventions.md`
