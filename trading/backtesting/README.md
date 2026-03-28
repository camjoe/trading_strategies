# Backtesting Layer Map

This package uses explicit layers to keep responsibilities clear.

## Entry Points

- `backtest.py`: public API and compatibility wrappers.
  - Orchestrates calls into service and repository layers.
  - Preserves stable function signatures used by CLI and backend.

## Layers

- `repositories/`: SQL and row retrieval/persistence only.
  - `backtest_repository.py`: write-side backtest run/trade/snapshot inserts.
  - `leaderboard_repository.py`: leaderboard row/equity reads.
  - `report_repository.py`: full report run/snapshot/trade reads.
  - `history_repository.py`: strategy-return history rows for auto-trader decisions.

- `services/`: business flow, model mapping, orchestration.
  - `backtest_data_service.py`: date resolution and market/universe data composition.
  - `history_service.py`: strategy-return loading and safe return calculations.
  - `leaderboard_service.py`: leaderboard computation and typed entry mapping.
  - `report_service.py`: full report assembly into typed report models.
  - `walk_forward_service.py`: walk-forward run orchestration and summary rollups.

- `domain/`: pure reusable backtesting logic.
  - `indicators_adapter.py`: indicator import adapter boundary for trends package.
  - `metrics.py`: drawdown and benchmark-return calculations.
  - `strategy_signals.py`: strategy signal rules and registry.
  - `windowing.py`: walk-forward date window generation.
  - `risk_warnings.py`: safeguard/warning policy composition.
  - `simulation_math.py`: position/cash/unrealized-PnL update math.

## Compatibility Modules

Top-level modules are retained as thin wrappers for backward compatibility:

- `backtest_data.py`
- `history.py`
- `strategy_signals.py`
- `indicators_adapter.py`

## Hook-Up Flow

1. Caller invokes `backtest.py` public function.
2. `backtest.py` delegates SQL to `repositories/` and mapping/orchestration to `services/`.
3. `services/` use `domain/` helpers for pure calculations.
4. Typed models remain in `trading/models/`; wrappers convert to legacy payloads where required.

## Naming Convention

- Repository modules end with `_repository.py` and live in `repositories/`.
- Service modules end with `_service.py` and live in `services/`.
- Domain helper modules live in `domain/` and use capability names (`metrics`, `windowing`, etc.).
