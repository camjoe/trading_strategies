# Backtesting Package Map

This package uses explicit layers to keep responsibilities clear.

## Purpose

Define ownership boundaries and interaction flow for backtesting repositories, services, and domain helpers.

## Entry Points

- `backtest.py`: public API entrypoint.
  - Orchestrates calls into service and repository layers.

## Layers

- `repositories/`: SQL and row retrieval/persistence only.
  - `backtest_repository.py`: write-side backtest run/trade/snapshot inserts.
  - `leaderboard_repository.py`: leaderboard row/equity reads.
  - `report_repository.py`: full report run/snapshot/trade reads.
  - `report_repository.py` also exposes recent run-list reads used by backend service adapters.
  - `walk_forward_repository.py`: walk-forward group and run persistence.

- `services/`: business flow, model mapping, orchestration.
  - `backtest_data_service.py`: date resolution and market/universe data composition.
  - `execution_service.py`: single-run backtest orchestration.
  - `leaderboard_service.py`: leaderboard computation and typed entry mapping.
  - `report_service.py`: full report assembly into typed report models.
  - `walk_forward_report_service.py`: persisted walk-forward report assembly.
  - `walk_forward_service.py`: walk-forward run orchestration and summary rollups.

- `domain/`: pure reusable backtesting logic.
  - `metrics.py`: drawdown and benchmark-return calculations.
  - `windowing.py`: walk-forward date window generation.
  - `risk_warnings.py`: safeguard/warning policy composition.
  - `simulation_math.py`: position/cash/unrealized-PnL update math.

- `models.py` (package root): typed dataclasses for result and config contracts. Key types: `BacktestConfig`, `BacktestResult`, `WalkForwardConfig`, `WalkForwardSummary`, `BacktestBatchConfig`. `BacktestResult` and `WalkForwardSummary` each expose a `to_payload(*, display_name_fn=None) -> dict` method that produces a JSON-ready dict; pass an optional `display_name_fn` to remap account names for UI presentation.

## Hook-Up Flow

1. Caller invokes `backtest.py` public function.
2. `backtest.py` delegates SQL to `repositories/` and mapping/orchestration to `services/`.
3. `services/` use `domain/` helpers for pure calculations.
4. Strategy signal dispatch uses `trading.domain.strategy_signals`; alternative strategies receive
   `ExternalFeatureBundle` values from `src/infrastructure/feature_providers/` providers.
5. Backtesting-local models live in `models.py` and `report_models.py`; shared cross-runtime
   contracts remain in `src/trading/models/`.

## Workflows

1. Start from `backtest.py` when tracing end-to-end execution.
2. Place SQL-only logic in `repositories/` and orchestration in `services/`.
3. Keep pure calculations in `domain/` and avoid persistence or transport concerns there.

## Naming Convention

- Repository modules end with `_repository.py` and live in `repositories/`.
- Service modules end with `_service.py` and live in `services/`.
- Domain helper modules live in `domain/` and use capability names (`metrics`, `windowing`, etc.).
