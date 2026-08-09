# Backtesting Map

Type: map
Status: Active
Created: 2026-08-07
Last Reviewed: 2026-08-08
Purpose: Inventory the `src/backtesting/` bounded context — the simulation and parameter-search subsystem that owns the backtest and optimizer tables, and the two service surfaces the trading side reads it through.
Related: [Trading Package Map](trading-package-map.md), [Backtesting](../reference/backtesting.md), [Architecture Conventions](../architecture/architecture-conventions.md)

## Purpose

`src/backtesting/` is a bounded context, not a layer — which is why it sits beside `src/trading/`
rather than inside it. The criterion is table ownership: it owns seven tables nothing else writes
(`backtest_runs`, `backtest_executions`, `backtest_equity_snapshots`, `optimization_experiments`,
`optimization_windows`, `optimization_trials`, `optimization_run_manifests`), and needs its own
`domain/services/repositories` stack to reach them.

It mirrors the same layering as `src/trading/`: services orchestrate, domain is side-effect free,
repositories hold the SQL.

## The seam with `trading/`

Enforced in both directions by `scripts/checks/repo/layer_check.py`.

| Direction | How it crosses |
|---|---|
| trading → backtesting | At **services**: `evidence` for a strategy's research evidence, `audit` for an experiment's record. One exception — `src/trading/services/strategy_catalog/optimizer_promotion.py` writes the promoted link inside the caller's transaction. |
| backtesting → trading | At **services**: `find_account`, `get_default_book`, `resolve_or_draft_strategy_record`. |

What backtesting takes from `trading.domain`, `trading.models`, and `trading.persistence` is
**layering, not crossing** — those are lower layers shared by everything. That includes
`domain.strategies.resolution`, which a backtest must share with the live path or it stops testing
the strategy that actually trades.

## Entry point

| Module | Responsibility |
|---|---|
| `composition.py` | Binds a caller-supplied market-data provider into a run (deriving the feature provider and the bar/benchmark fetches). The application builds the provider — one per invocation, so the adapter's cumulative call guard spans the whole sweep. Read surfaces are imported from `services/` directly. |

## `domain/`

Side-effect free: no I/O, no SQL, no service calls.

| Module | Responsibility |
|---|---|
| `bars.py` | Bar-series shaping and access helpers |
| `metrics.py` | Performance math over an equity curve (returns, drawdown, Sharpe, exposure), plus `equity_curve_from_rows` to lift a curve out of snapshot rows |
| `risk_warnings.py` | Config-level warnings raised before a run executes |
| `windowing.py` | A run's date window: resolving it from a range or lookback, month arithmetic, and walk-forward train/test split construction |
| `optimization.py` | Candidate generation and `params_fingerprint`, the `calmar_v1` objective and winner selection, and compounding per-window OOS results into one series |

## `services/`

| Module | Responsibility |
|---|---|
| `simulation.py` | Run one backtest: price the universe, evaluate signals, simulate fills, persist the run. Also previews a run's warnings off the same resolved scope |
| `run_inputs.py` | Read a run's inputs from outside: its universe (`RunUniverse`) from ticker files, its bars and benchmark closes from the provider |
| `walk_forward_optimizer.py` | Drive a walk-forward parameter search (grid → freeze-on-train → OOS → holdout). Writes nothing — it returns an `OptimizationSummary` |
| `optimization_experiment.py` | Run that search and persist what it found: the experiment row, its per-window/per-candidate audit tree, and the frozen manifest. A failed sweep still gets a row |
| `optimizer_aggregation.py` | Read-side aggregation over a persisted experiment (OOS segments, compounded series). Internal to this package — the two seams read it, nothing outside does |
| `reporting.py` | Every operator-facing read over persisted runs: one run's full report or summary, the run listings, and the leaderboard that ranks runs against each other. Benchmark and alpha come from the run row, so none of it needs market data |
| `evidence.py` | **Seam.** A strategy's backtest and walk-forward evidence as one pair of `Evaluation*Evidence` records, off a single experiment lookup |
| `audit.py` | **Seam.** One experiment's audit record, plus the recent-experiments listing. The listing forwards to the repository unchanged — `layer_check` bars `src/trading/` from reaching the tables itself, and its one caller joins account names, which backtesting does not own |

## `repositories/`

SQL only. The seven owned tables.

| Module | Responsibility |
|---|---|
| `runs.py` | Backtest run rows (including the benchmark frozen at run time, revision `0030`), their executions and equity snapshots — writes plus the report, recent-run, and leaderboard reads |
| `optimization.py` | Optimizer experiments, windows, trials, and run manifests |

## `models/`

Passive contracts, one module per area. The package root re-exports the stable public types,
mirroring `trading/models/`. These belong to the seven tables this context owns; `trading/models/`
holds the contracts for the tables `trading/repositories/` owns.

| Module | Responsibility |
|---|---|
| `backtest.py` | A run's config, resolved universe, and result (`BacktestConfig`, `RunUniverse`, `BacktestResult`, `BacktestBatchConfig`) plus the run-purpose vocabulary |
| `optimizer.py` | Walk-forward search config and everything an experiment persists — experiment, window, trial, and manifest `*Insert`/`*Record` pairs — plus the shapes derived from them on read: OOS aggregation and the `ExperimentAudit` tree |
| `report.py` | Report, run-listing, and leaderboard shapes returned to operator surfaces |

## Related

- [Backtesting](../reference/backtesting.md) — how the engine works and what it guarantees
- [Backtest/Live Divergence](../reference/backtest-live-divergence.md) — where simulation and live execution differ
- [`src/backtesting/README.md`](../../src/backtesting/README.md)
