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

There is no single entrypoint. `composition.py` binds a market-data provider into a run: the caller
supplies one, and it derives the feature provider and the bar/benchmark fetches from it.

**The provider is built by the application, not here** — `cli/main.py`, the web routes, and
`scripts/benchmark_sweep.py` each build one per invocation and pass it down. That placement is load
bearing: a provider carries per-instance call guards (the yfinance adapter's rate limiter caps
cumulative calls for its own lifetime), so building one per run would reset them on every run, and
an optimizer sweep runs a backtest per candidate per window.

Go through `composition.py` to run a backtest or a batch. Import everything else from the service
that owns it: reports, leaderboards, evidence, audits, and the optimizer all read persisted rows and
need no provider.

## Layers

- `repositories/`: SQL and row retrieval/persistence only. One module per data area, as in
  `trading/repositories/`.
  - `runs.py`: `backtest_runs`, `backtest_executions`, and `backtest_equity_snapshots` — run/trade/snapshot
    inserts plus the report, recent-run, and leaderboard reads over them.
  - `optimization.py`: `optimization_experiments`, `optimization_windows`, `optimization_trials`, and
    `optimization_run_manifests` — experiment config, winner, holdout summary, promoted link, and the
    per-window/per-candidate audit tree.

- `services/`: business flow, model mapping, orchestration.
  - `backtest_data_service.py`: date resolution and market/universe data composition. `fetch_bar_history`
    is the engine's only market-data read — the benchmark series is derived from it, so a run has one
    price path and one set of gap-filling rules.
  - `simulation_service.py`: run one backtest — resolve inputs, simulate the bars, persist the run.
    Also previews the warnings a run would raise, sharing the resolution the run itself uses.
  - `leaderboard_service.py`: leaderboard computation and typed entry mapping, over the same
    frozen benchmark.
  - `report_service.py`: report assembly into typed report models — the full report, the summary
    alone for listings, and the run-header reads behind them. Needs no market-data provider — a
    run's benchmark return is read from its row, frozen there when it executed.
  - `walk_forward_optimizer_service.py`: walk-forward optimization orchestration (grid → freeze-on-train → OOS/holdout) and Tier-1 experiment persistence.
  - `evidence_service.py`: **the seam.** A strategy's backtest and walk-forward evidence as one pair,
    so evaluation never has to know how runs, holdouts, and experiments relate.
  - `audit_service.py`: **the seam.** One experiment's audit record, plus the recent-experiments list.

- `domain/`: pure reusable backtesting logic.
  - `bars.py`: aligns per-ticker daily bar frames onto one trading calendar (`BarPanel`).
  - `metrics.py`: drawdown and benchmark-return calculations, plus `equity_curve_from_rows`.
  - `windowing.py`: month arithmetic and walk-forward optimization train/test/holdout splits.
  - `risk_warnings.py`: safeguard/warning policy composition.
  - `simulation_math.py`: position/cash/unrealized-PnL update math.
  - `optimization/`: candidate search, objective scoring, and OOS aggregation. The *promotion gate*
    is not here — it is promotion policy, so it lives at `trading/domain/promotion_gate.py`.

- `models/`: passive contracts, one module per area — `backtest.py` (a run's config and result),
  `optimizer.py` (search config, everything an experiment persists, and the audit/OOS shapes derived
  from those rows on read), `report.py` (operator-facing
  report and leaderboard shapes). The package root re-exports the stable public types, mirroring
  `trading/models/`. `BacktestResult` and `OptimizationSummary` each expose
  `to_payload(*, display_name_fn=None) -> dict`; pass `display_name_fn` to remap account names for
  UI presentation.

## Hook-Up Flow

1. The application builds a market-data provider and hands it to `composition.py` to run a
   backtest; every other caller imports the owning service directly.
2. `composition.py` binds that provider into `simulation_service.run_backtest`; each service
   reaches its own tables through `repositories/`.
3. `services/` use `domain/` helpers for pure calculations.
4. Strategy signal dispatch uses `trading.domain.strategies` (e.g. `resolution.resolve_strategy`);
   alternative strategies receive `ExternalFeatureBundle` values from
   `src/infrastructure/feature_providers/` providers.
5. Backtesting-local models live in `models/`; shared cross-runtime
   contracts remain in `src/trading/models/`.

## Workflows

1. Start from `composition.py` when tracing a run end to end; start from the service when tracing a read.
2. Place SQL-only logic in `repositories/` and orchestration in `services/`.
3. Keep pure calculations in `domain/` and avoid persistence or transport concerns there.

## Naming Convention

- Repository modules live in `repositories/` and are named for the data area they own
  (`runs`, `optimization`) — the same convention as `trading/repositories/`, with no `_repository` suffix.
- Service modules end with `_service.py` and live in `services/`.
- Domain helper modules live in `domain/` and use capability names (`metrics`, `windowing`, etc.).
