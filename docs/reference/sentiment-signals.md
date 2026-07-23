# Sentiment and Alternative Signal Reference

Type: notes
Status: Active
Created: 2026-03-30
Last Reviewed: 2026-07-17
Purpose: Capture the current architecture and extension points for alternative-data signals used in strategy execution.
Related: [Strategy Catalog](strategies.md), [Trading Package Map](../maps/trading-package-map.md)

## Purpose

Capture the current architecture and extension points for alternative-data
signals used by strategy execution.

This document intentionally focuses on current behavior. It is not a phase
history or backlog tracker.

## Scope

This reference covers:

- `policy_regime`
- `news_sentiment`
- `social_trend_rotation`
- live feature injection for alternative strategies

Strategy catalog details (all strategy families) live in:

- `docs/reference/strategies.md`

## Current Architecture

Signal dispatch and registration:

- `src/trading/domain/strategies/` owns `STRATEGY_REGISTRY` (`registry.py`) and
  `resolve_signal()` dispatch (`resolution.py`).
- The three alternative strategies above are registered with
  `strategy_style="alternative"`.

Provider boundary:

- `src/trading/domain/feature_provider.py` defines `ExternalFeatureProvider` and
   `ExternalFeatureBundle`.
- Concrete provider ownership:

| Strategy | Provider | Feature source |
|---|---|---|
| `policy_regime` | `src/infrastructure/feature_providers/policy_provider.py` | ETF proxy returns such as TLT/GLD/XLU/UUP vs SPY |
| `news_sentiment` | `src/infrastructure/feature_providers/news_provider.py` | RSS headlines plus optional NewsAPI supplementation, scored with VADER |
| `social_trend_rotation` | `src/infrastructure/feature_providers/social_provider.py` | Google Trends interest plus Reddit mention/sentiment data |

- Feature-provider imports are isolated to `src/infrastructure/feature_providers/`.

Market-data dependency:

- `src/infrastructure/market_data/factory.py` resolves and builds the configured
  market-data provider (injected at composition seams; no global locator).
- Alternative providers consume market/news/social data through their own
  provider logic; strategy functions consume normalized bundles only.

## Runtime Behavior and Guardrails

Degradation contract:

- providers should degrade gracefully (no hard failure in normal strategy flow)
- when required features are unavailable, strategy logic returns conservative
  behavior (typically `hold`)

Live strategy execution:

- `src/trading/services/execution/selection/selection.py` builds per-ticker feature
   history for alternative strategies with `build_feature_history_fn`.
- `policy_regime` uses the configured policy fetcher, `news_sentiment` uses the
  configured news fetcher, and `social_trend_rotation` uses the configured
  social fetcher. Missing or failing providers return no feature history, so
  the signal functions degrade to conservative behavior.
- Regime/news/social rotation overlays were retired after the runtime converged on the single
  book-keyed decision-score path. The providers and alternative-strategy signals remain supported;
  reintroducing regime-aware rotation must extend the current book rotation model rather than
  restore the retired account-level selection branch.

Operator visibility:

- The `alt-strategies` UI tab exposes provider status and feature-only signal
  inspection.
- Backend orchestration lives in `apps/paper_trading_web/backend/services/features/`.
- Feature-only UI signal inspection intentionally omits live price history, so
  price-momentum guards remain active and the response reports `available:
  false` even when provider features are present.

## Related References

- `docs/reference/strategies.md`
- `docs/reference/backtesting.md`
- `src/trading/README.md`
- `docs/architecture/architecture-conventions.md`
