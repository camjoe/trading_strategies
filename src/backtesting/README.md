# Backtesting Package Map

A **bounded context**, not a layer — which is why it sits at `src/backtesting/`, beside
`src/trading/` rather than inside it. The criterion is table ownership: it owns seven tables
(`backtest_runs`, `backtest_executions`, `backtest_equity_snapshots`,
`optimization_experiments`, `optimization_windows`, `optimization_trials`,
`optimization_run_manifests`) whose only runtime writer is `repositories/` here, and it needs its
own layered stack to reach them.

Two things this boundary is *not*. It is not schema isolation: `backtest_runs` and
`optimization_experiments` carry foreign keys into `accounts` and `strategies`, and deleting an
account cascades into both. And it is not write exclusivity in the literal sense —
`trading/repositories/fixture_seed.py` writes the three `backtest_*` tables when generating a demo
or sandbox database, because a fixture needs research records no operator flow produces. What the
boundary asserts is narrower and still true: on the runtime path, these seven tables have one
writer, and it lives here.

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

- `services/`: business flow, model mapping, orchestration. Import from the owning module; the
  package root re-exports nothing.
  - `run_inputs.py`: reads a run's inputs from outside — its universe (as a
    `RunUniverse`) from ticker files, its bars and benchmark closes from the provider.
    `fetch_bar_history` is the only market-data read; the benchmark series is derived from it, so a
    run has one price path and one set of gap-filling rules. The date window is pure arithmetic and
    lives in `domain/windowing.py`.
  - `simulation.py`: run one backtest — resolve scope, fetch bars, simulate, persist. Also
    previews a run's warnings: preview and run resolve their scope through the same function, so
    they cannot disagree about what they warn on.
  - `reporting.py`: every operator-facing read over persisted runs — one run's full report or
    summary, the run listings, and the leaderboard. Same three tables and same performance math
    throughout. Needs no market-data provider: a run's benchmark return is read from its row,
    frozen there when it executed.
  - `walk_forward_optimizer.py`: the walk-forward search itself (grid → freeze-on-train →
    OOS → holdout). Persists nothing and touches no repository, so a benchmark harness can run a
    full sweep without writing an experiment.
  - `optimization_experiment.py`: runs that search and writes what it found — the
    experiment row, its audit tree, and the frozen provenance manifest.
  - `evidence.py`: **the seam.** A strategy's backtest and walk-forward evidence as one pair,
    so evaluation never has to know how runs, holdouts, and experiments relate.
  - `audit.py`: **the seam.** One experiment's audit record, plus the recent-experiments list.
  - `optimizer_aggregation.py`: not a seam — the OOS segments and compounded series the two
    seams above read. Derived on each read, never stored.

- `domain/`: pure reusable backtesting logic.
  - `bars.py`: aligns per-ticker daily bar frames onto one trading calendar (`BarPanel`).
  - `metrics.py`: drawdown and benchmark-return calculations, plus `equity_curve_from_rows`.
  - `windowing.py`: a run's date window — resolved from an explicit range or a lookback — plus month
    arithmetic and walk-forward train/test/holdout splits.
  - `risk_warnings.py`: safeguard/warning policy composition.
  - Fill and valuation math are **not** here. `trading/domain/accounting.py` owns the buy/sell
    ledger primitives and `trading/domain/portfolio_math.py` owns market value and unrealized
    P&L, both shared with the live runtime so a simulated fill costs and realizes what a real
    one does — see [ADR 020](../../docs/adr/020-shared-financial-math-ownership.md).
  - `optimization.py`: candidate search, objective scoring, and OOS aggregation. The *promotion gate*
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
2. `composition.py` binds that provider into `simulation.run_backtest`; each service
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

- Modules are named for what they own, with no layer suffix — the directory already says the
  layer. `repositories/runs.py`, not `runs_repository.py`; `services/reporting.py`, not
  `reporting_service.py`.
- Domain helper modules use capability names (`metrics`, `windowing`, etc.).
