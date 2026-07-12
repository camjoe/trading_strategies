# Sentiment and Alternative Signal Reference

Type: notes
Status: Active
Created: 2026-03-30
Last Reviewed: 2026-04-25
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

- `src/trading/domain/strategy_signals.py` owns `STRATEGY_REGISTRY` and
  `resolve_signal()` dispatch.
- The three alternative strategies above are registered with
  `strategy_style="alternative"`.

Provider boundary:

- `src/trading/domain/feature_provider.py` defines `ExternalFeatureProvider` and
  `ExternalFeatureBundle`.
- Concrete providers:
  - `src/infrastructure/feature_providers/policy_provider.py`
  - `src/infrastructure/feature_providers/news_provider.py`
  - `src/infrastructure/feature_providers/social_provider.py`
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

- `src/trading/services/auto_trading/execution.py` builds per-ticker feature
  history for alternative strategies with `build_feature_history_fn`.
- `news_sentiment` uses the configured news fetcher; `social_trend_rotation`
  uses the configured social fetcher. Missing or failing providers return no
  feature history, so the signal functions degrade to conservative behavior.
- Regime/news/social rotation overlays were retired; see
  `docs/adr/009-regime-overlay-rotation-retired.md` for the preserved design.

Operator visibility:

- UI feature status and signal inspection are exposed via
  `paper_trading_web` feature routes/services.

## Not Implemented in This Slice

Still out of scope for the current implementation:

- historical sentiment feature store for backfill/replay
- event-calendar and earnings-driver integrations
- insider-flow and unusual-options-flow datasets
- experiment-tracking infrastructure for model research workflows

## Related References

- `docs/reference/strategies.md`
- `docs/reference/backtesting.md`
- `src/trading/README.md`
- `docs/architecture/architecture-conventions.md`
