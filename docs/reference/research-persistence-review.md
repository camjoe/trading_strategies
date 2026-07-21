# Program A — Backtest and Walk-Forward Schema Plan

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: Track the accepted schema-hygiene and atomic-persistence work that puts the existing backtest and walk-forward tables in good shape, independent of the later walk-forward optimizer.
Related: [Program B — Walk-Forward Optimizer Plan](walk-forward-optimization-plan.md), [Backtesting](backtesting.md), [Database Transactions](database-transactions.md), [Database Schema](db-schema.md), [Database Diagram Decisions](database-diagram-decisions.md)

## Purpose

This is the canonical tracker for **Program A — schema in good shape**: the atomicity and
schema-hygiene work on the existing research tables. It is a self-contained program that can ship and
be declared done on its own.

Scope of Program A:

- `backtest_runs` — add a run `purpose` discriminator and fix atomic persistence;
- `backtest_trades` / `backtest_equity_snapshots` — rename to honest names;
- `walk_forward_groups` / `walk_forward_group_runs` — rename, and stop copying child aggregates;
- purpose-aware read queries so evidence kinds are not silently mixed.

The later **walk-forward optimizer** — training, candidate trials, out-of-sample and holdout evidence,
manifests, and the optimizer schema — is a separate program tracked in
[Program B — Walk-Forward Optimizer Plan](walk-forward-optimization-plan.md), to be implemented on its
own branch. Program B depends on Program A having merged.

## Current State

The current model is a compact foundation:

- `backtest_runs` is the simulation aggregate root.
- Executions and daily equity snapshots are normalized children with cascading ownership.
- Rolling-window evaluation reuses normal backtest output instead of creating a parallel result format.
- Fees, slippage, prior-day signals, and next-bar execution are represented consistently.
- Persisted snapshots allow metrics to be recalculated.

The limitations Program A fixes:

- the run header commits before all children, so an interrupted run can appear complete;
- rolling-window runs are indistinguishable from standalone runs;
- several names describe the implementation poorly (`backtest_trades` rows are single executions, not
  round-trip trades; `trade_time`/`snapshot_time` hold daily dates; `grouping_key` identifies an
  experiment);
- copied window/experiment aggregate metrics can drift from their source runs.

Two further limitations — that persisted rows cannot reproduce a run, and that the workflow is
rolling-window robustness testing rather than train-optimize-test optimization — are motivations for
[Program B](walk-forward-optimization-plan.md) and are out of scope here.

The five research tables held no rows in the live database on 2026-07-21 and are expected to remain
empty. Any rows that might exist carry no methodology, purpose, or reproducibility metadata worth
preserving, so Program A's migration drops and recreates the affected tables instead of carrying legacy
rows forward. There is no backfill, no `legacy_incomplete` labeling, and no legacy-data-loss surface on
downgrade.

## Delivery Strategy

Program A is two phases:

1. Make completed backtest persistence atomic without changing the schema.
2. Apply one hygiene migration (renames, `purpose`, drop copied aggregates) with the repository cutover
   and purpose-aware read queries.

A phase is complete only when its schema, repositories, behavior, tests, and documentation agree.

## Accepted Architecture

### Atomic completed runs

Failed backtests have no current product use and must leave no partial result tree.

- Fetch external market, benchmark, universe, and feature data before opening the write transaction.
- Convert participating repository commits to `commit_unit_of_work`.
- Wrap the run header, executions, snapshots, and final outputs in one `unit_of_work`.
- A successful standalone run still commits once and remains immediately reportable.
- Do not add a `backtest_runs` lifecycle merely to preserve failures.

This uses the interleaved simulation/write flow accepted during planning. The transaction covers the
simulation loop but not external network or provider I/O.

### Shared run aggregate and purpose

Keep `backtest_runs` as the reusable simulation root and add a required `purpose` discriminator so
rolling-window runs are distinguishable from standalone runs and, later, from optimizer evidence.

Accepted purposes:

- `standalone`;
- `rolling_window`;
- `walk_forward_oos` (produced by Program B);
- `final_holdout` (produced by Program B).

The `purpose` column and its `CHECK` are added now, enumerating all four values even though only
`standalone` and `rolling_window` are produced until Program B. Queries must request the evidence
purpose they intend to consume; a generic "latest run" must not silently mix purposes.

### Final entity names

Apply these renames as part of the hygiene migration:

| Current | Final | Reason |
|---|---|---|
| `walk_forward_groups` | `walk_forward_experiments` | The row owns methodology and experiment lifecycle. |
| `walk_forward_group_runs` | `walk_forward_windows` | The row owns one chronological train/test window. |
| `backtest_trades` | `backtest_executions` | Each row is one simulated buy or sell, not a round-trip trade. |
| `trade_time` | `execution_date` | The simulator has daily rather than intraday resolution. |
| `snapshot_time` | `snapshot_date` | Equity snapshots have daily resolution. |
| `grouping_key` | `experiment_key` | The key identifies an experiment. |

Use `execution_count` in new internal contracts. Preserve the existing `tradeCount` transport alias so
the unchanged web client does not break, and assert the alias in the contract tests.

### Metric ownership

- Executions and equity snapshots are authoritative run outputs.
- Window and experiment aggregate return fields are derived from their member runs at query time rather
  than copied into the experiment/window tables. Program A removes the copied
  `average/median/best/worst_return_pct` columns and derives them on read.

## Program A Schema Migration

The hygiene migration should:

- drop and recreate the affected research tables rather than carrying legacy rows forward (see
  [Current State](#current-state)); no backfill and no `legacy_incomplete` labeling;
- apply the accepted table and column renames as part of that recreation;
- add a required `purpose` discriminator to `backtest_runs`, constrained by
  `CHECK (purpose IN ('standalone', 'rolling_window', 'walk_forward_oos', 'final_holdout'))`;
- remove the copied window/experiment aggregate columns and the redundant existing group/window index;
- otherwise keep the `walk_forward_experiments` / `walk_forward_windows` shape minimal.

The optimizer columns (methodology, training policy, boundaries, selection, lifecycle), the new
`optimization_trials` table, and the `backtest_runs` manifest/provenance fields are **Program B's
migration**, not this one. Because Program A merges first, the two migrations do not need to be
coordinated; Program B adds its own numbered migration on top.

Because the tables are recreated empty, there is no forward backfill and no reproducibility labeling.
The downgrade simply recreates the prior table shapes; no research rows are preserved in either
direction, so there is no data-loss surface beyond the empty-table note.

## Implementation Phases

### Phase 1: Atomic persistence

- Change participating backtest writes to `commit_unit_of_work`.
- Wrap all run result writes in a post-I/O `unit_of_work`.
- Add failure injection at the header, execution, snapshot, and finalization boundaries.

Developer verification: every injected failure leaves all research result tables unchanged.

### Phase 2: Hygiene schema and purpose-aware reads

- Add passive contracts for run purposes and the renamed row shapes.
- Implement the drop-and-recreate hygiene migration and cut repositories over in the same phase.
- Make existing read queries (latest-run, leaderboard, evaluation) purpose-aware as soon as the
  discriminator exists, so no consumer silently mixes evidence purposes.
- Derive window/experiment aggregates at query time instead of reading copied columns.
- Preserve the `tradeCount` transport alias and assert it in the contract tests.

Developer verification: the schema description shows unambiguous ownership, the `purpose` enumeration,
and the renamed columns; a latest-run query for one purpose never returns another purpose's rows; the
web client still receives `tradeCount`.

## Validation and Completion Criteria

Minimum validation includes:

- migration upgrade/downgrade on empty tables (drop-and-recreate; no backfill);
- rollback at every backtest persistence boundary;
- purpose-aware query and repository constraints;
- derived (not copied) window/experiment aggregates reconciled against member runs;
- `tradeCount` transport alias preserved.

Program A is complete when both phases pass their focused tests and the full repository checks, and the
documentation describes implemented behavior rather than intent. The walk-forward optimizer, manifests,
optimizer schema, and CLI optimizer operations are out of scope and belong to
[Program B](walk-forward-optimization-plan.md).

## Progress Tracker

| Phase | State | Delivered |
|---|---|---|
| Documentation baseline | Complete | Program A scope separated from the optimizer program. |
| Atomic persistence | Complete | Run header, executions, and snapshots wrapped in one post-I/O `unit_of_work`; failure-injection tests at each write boundary. |
| Hygiene schema and purpose-aware reads | Complete | Migration `0016` (renames, `purpose` + CHECK, dropped aggregates); repository cutover with transport-stable aliases; purpose-aware standalone reads; experiment/window aggregates derived at read time. |

## Boundaries

- Do not retain failed or partial backtest output trees.
- Do not let rolling-window, failed, or incomplete runs silently enter standalone evidence.
- Do not call the current rolling-window workflow full walk-forward optimization.
- Do not copy child aggregate metrics into the experiment/window tables; derive them.
- Do not add optimizer tables, manifest fields, or optimizer columns in Program A's migration — those
  are Program B's.

## Related Docs

- [Program B — Walk-Forward Optimizer Plan](walk-forward-optimization-plan.md)
- [Backtesting reference](backtesting.md)
- [Database transactions](database-transactions.md)
- [Database schema](db-schema.md)
- [Database diagram decisions](database-diagram-decisions.md)
- [Architecture conventions](../architecture/architecture-conventions.md)
