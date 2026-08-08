# Backtesting Package Map

A **bounded context**, not a layer — which is why it sits at `src/backtesting/`, beside
`src/trading/` rather than inside it. The criterion is table ownership: it owns seven tables nothing
else writes (`backtest_runs`, `backtest_executions`, `backtest_equity_snapshots`,
`optimization_experiments`, `optimization_windows`, `optimization_trials`,
`optimization_run_manifests`), and needs its own layered stack to reach them.

For the module-by-module inventory and the seam rules, see the
[Backtesting Map](../../docs/maps/backtesting-map.md). This file covers ownership boundaries and
interaction flow.

## Purpose

Define ownership boundaries and interaction flow for backtesting repositories, services, and domain helpers.

## Entry Points

- `backtest.py`: supported internal package entrypoint.
  - Orchestrates calls into service and repository layers.

## Layers

- `repositories/`: SQL and row retrieval/persistence only.
  - `backtest_repository.py`: write-side backtest run/trade/snapshot inserts.
  - `leaderboard_repository.py`: leaderboard row/equity reads.
  - `report_repository.py`: full report run/snapshot/trade reads.
  - `report_repository.py` also exposes recent run-list reads used by backend service adapters.
  - `optimization_repository.py`: walk-forward optimization experiment persistence (Tier-1: config, winner, holdout summary, promoted link).

- `services/`: business flow, model mapping, orchestration.
  - `backtest_data_service.py`: date resolution and market/universe data composition. `fetch_bar_history`
    is the engine's read; `fetch_close_history` still serves the benchmark series and the proxy
    feature provider.
  - `execution_service.py`: single-run backtest orchestration.
  - `leaderboard_service.py`: leaderboard computation and typed entry mapping.
  - `report_service.py`: full report assembly into typed report models.
  - `walk_forward_optimizer_service.py`: walk-forward optimization orchestration (grid → freeze-on-train → OOS/holdout) and Tier-1 experiment persistence.
  - `evidence_service.py`: **the seam.** A strategy's backtest and walk-forward evidence, joined and
    summarized here so evaluation never has to know how runs, holdouts, and experiments relate.
  - `audit_service.py`: **the seam.** One experiment's audit record, plus the recent-experiments list.

- `domain/`: pure reusable backtesting logic.
  - `bars.py`: aligns per-ticker daily bar frames onto one trading calendar (`BarPanel`).
  - `metrics.py`: drawdown and benchmark-return calculations.
  - `windowing.py`: month arithmetic and walk-forward optimization train/test/holdout splits.
  - `risk_warnings.py`: safeguard/warning policy composition.
  - `simulation_math.py`: position/cash/unrealized-PnL update math.
  - `optimization/`: candidate search, objective scoring, and OOS aggregation. The *promotion gate*
    is not here — it is promotion policy, so it lives at `trading/domain/promotion_gate.py`.

- `models/`: passive contracts, one module per area — `backtest.py` (a run's config and result),
  `optimizer.py` (search config and everything an experiment persists), `report.py` (operator-facing
  report and leaderboard shapes). The package root re-exports the stable public types, mirroring
  `trading/models/`. `BacktestResult` and `OptimizationSummary` each expose
  `to_payload(*, display_name_fn=None) -> dict`; pass `display_name_fn` to remap account names for
  UI presentation.

## Hook-Up Flow

1. Caller invokes the supported function in `backtest.py`.
2. `backtest.py` delegates SQL to `repositories/` and mapping/orchestration to `services/`.
3. `services/` use `domain/` helpers for pure calculations.
4. Strategy signal dispatch uses `trading.domain.strategies` (e.g. `resolution.resolve_strategy`);
   alternative strategies receive `ExternalFeatureBundle` values from
   `src/infrastructure/feature_providers/` providers.
5. Backtesting-local models live in `models/`; shared cross-runtime
   contracts remain in `src/trading/models/`.

## Workflows

1. Start from `backtest.py` when tracing end-to-end execution.
2. Place SQL-only logic in `repositories/` and orchestration in `services/`.
3. Keep pure calculations in `domain/` and avoid persistence or transport concerns there.

## Naming Convention

- Repository modules end with `_repository.py` and live in `repositories/`.
- Service modules end with `_service.py` and live in `services/`.
- Domain helper modules live in `domain/` and use capability names (`metrics`, `windowing`, etc.).
