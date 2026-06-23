# Sentiment and Alternative Signal Reference

Type: notes
Status: Active
Created: 2026-03-30
Last Reviewed: 2026-04-25
Purpose: Capture the current architecture and extension points for alternative-data signals used in strategy execution.
Related: [Strategy Catalog](strategies.md), [Trading Package Map](../maps/trading-package-map.md)

## Purpose

Capture the current architecture and extension points for alternative-data
signals used by strategy execution and rotation overlays.

This document intentionally focuses on current behavior. It is not a phase
history or backlog tracker.

## Scope

This reference covers:

- `policy_regime`
- `news_sentiment`
- `social_trend_rotation`
- account-level news/social overlay behavior for regime rotation

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

- `src/trading/services/market_data/registry.py` resolves the configured market-data
  provider.
- Alternative providers consume market/news/social data through their own
  provider logic; strategy functions consume normalized bundles only.

## Runtime Behavior and Guardrails

Degradation contract:

- providers should degrade gracefully (no hard failure in normal strategy flow)
- when required features are unavailable, strategy logic returns conservative
  behavior (typically `hold`)

Rotation overlays:

- `src/trading/services/auto_trading/rotation.py` applies news/social overlay votes
  when `rotation_overlay_mode` is enabled.
- Overlay coverage uses the union of current holdings and
  `rotation_overlay_watchlist`.
- Overlay watchlist defaults are seeded from `src/infrastructure/config/trade_universe.txt`
  at schema/default time. Changing that file later does not automatically
  update already-migrated DB values.

Operator visibility:

- UI feature status and signal inspection are exposed via
  `paper_trading_ui` feature routes/services.

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
