# Research Persistence and Walk-Forward Completion Plan

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: Track the accepted architecture, implementation sequence, and completion criteria for reproducible backtest and walk-forward research persistence.
Related: [Backtesting](backtesting.md), [Walk-Forward Optimization Plan](walk-forward-optimization-plan.md), [Database Transactions](database-transactions.md), [Database Schema](db-schema.md), [Database Diagram Decisions](database-diagram-decisions.md)

## Purpose

This document is the canonical implementation tracker for improving:

- `backtest_runs`;
- `backtest_trades` and `backtest_equity_snapshots`;
- `walk_forward_groups` and `walk_forward_group_runs`;
- the connection between persisted research, evaluation, and promotion.

It combines the 2026-07-21 persistence review with the decisions made from that review. Use the
[Walk-Forward Optimization Plan](walk-forward-optimization-plan.md) for detailed methodology and
leakage controls. Use this document for delivery order, schema ownership, and progress.

## Current State

The current model is a compact foundation:

- `backtest_runs` is the simulation aggregate root.
- Executions and daily equity snapshots are normalized children with cascading ownership.
- Rolling-window evaluation reuses normal backtest output instead of creating a parallel result
  format.
- Fees, slippage, prior-day signals, and next-bar execution are represented consistently.
- Persisted snapshots allow metrics to be recalculated.

The important limitations are:

- the run header commits before all children, so an interrupted run can appear complete;
- persisted rows do not freeze enough configuration, data, universe, feature, benchmark, or code
  input to reproduce a run;
- rolling-window runs are indistinguishable from standalone runs;
- the current workflow is rolling-window robustness evaluation, not train-optimize-test
  walk-forward optimization;
- several names describe the implementation poorly, and copied aggregate metrics can drift.

The live database contained no rows in the five reviewed research tables on 2026-07-21. Migrations
must still preserve legacy data correctly rather than relying on that observation.

## Delivery Strategy

Do not implement this table by table. Table-level changes are coupled by run purpose, provenance,
experiment ownership, evidence queries, and deletion behavior. Also do not hold every improvement
until the full optimizer is ready.

Use this sequence:

1. Make completed backtest persistence atomic without changing the schema.
2. Freeze the end-state contracts across runs, artifacts, experiments, windows, and trials.
3. Apply one coordinated schema migration and repository cutover.
4. Add immutable inputs and parameterized simulation.
5. Implement training, selection, OOS execution, and final holdout as vertical workflows.
6. Cut reports, evaluation, promotion, and CLI operations over to the new evidence model.

A phase is complete only when its schema, repositories, behavior, tests, and documentation agree.

## Accepted Architecture

### Atomic completed runs

Failed backtests have no current product use and must leave no partial result tree.

- Fetch external market, benchmark, universe, and feature data before opening the write
  transaction.
- Convert participating repository commits to `commit_unit_of_work`.
- Wrap the run header, executions, snapshots, and final outputs in one `unit_of_work`.
- A successful standalone run still commits once and remains immediately reportable.
- Do not add a `backtest_runs` lifecycle merely to preserve failures.

This uses the interleaved simulation/write flow accepted during planning. The transaction therefore
covers the simulation loop, but it does not cover external network or provider I/O.

### Shared run aggregate

Keep `backtest_runs` as the reusable simulation root and add a required purpose discriminator.
Experiment tables own orchestration and membership; the run table owns one complete simulator
result.

Accepted purposes:

- `standalone`;
- `rolling_window`;
- `walk_forward_oos`;
- `final_holdout`.

Training candidates persist summaries and reproducibility inputs in `optimization_trials`; they do
not create full execution and equity trees.

Queries must request the evidence purpose they intend to consume. A generic "latest run" must not
silently mix standalone, rolling-window, OOS, and holdout evidence.

### Final entity names

Apply the following renames together after the architecture contracts are ready:

| Current | Final | Reason |
|---|---|---|
| `walk_forward_groups` | `walk_forward_experiments` | The row owns methodology and experiment lifecycle. |
| `walk_forward_group_runs` | `walk_forward_windows` | The row owns one chronological train/test window. |
| `backtest_trades` | `backtest_executions` | Each row is one simulated buy or sell, not a round-trip trade. |
| `trade_time` | `execution_date` | The simulator has daily rather than intraday resolution. |
| `snapshot_time` | `snapshot_date` | Equity snapshots have daily resolution. |
| `grouping_key` | `experiment_key` | The key identifies an experiment. |

Use `execution_count` in new internal contracts. Preserve the existing `tradeCount` transport alias
where needed so the unchanged web client does not break.

### Run manifests and immutable artifacts

`book_strategy_history` and `book_universe_history` remain useful lineage sources, but they cannot
reproduce a run by themselves. At execution time, resolve effective state and freeze it into a
versioned run manifest.

The manifest includes:

- strategy identity and exact validated parameters;
- effective account/book settings that affect simulation;
- initial cash, benchmark, dates, fees, slippage, warm-up, and execution policies;
- exact universe membership and its source lineage;
- market and external-feature provider/as-of metadata;
- engine version, application build, source revision, and dirty-state provenance;
- referenced artifact hashes and manifest schema version.

Store actual research inputs through an artifact-storage port. The initial backend is a local,
content-addressed store under `local/`; database rows store URI, SHA-256, format version, byte size,
and ownership relationships. The initial deterministic format is
`research-input-json-gzip-v1`. Its canonical uncompressed JSON bytes are hashed, and compression
must use normalized metadata so identical inputs deduplicate.

Artifacts include the price, benchmark, universe, and external-feature inputs required for offline
replay. Referenced artifacts have no automatic pruning policy. A run is eligible for promotion only
when its manifest and artifacts are complete.

### Metric ownership

- Executions and equity snapshots are authoritative run outputs.
- Window return and experiment aggregate fields are derived from their OOS runs rather than copied
  into multiple tables.
- Trial metrics remain persisted because they are the evidence used to rank candidates.
- Metric and objective versions live at the owning run, trial, or experiment boundary rather than
  being repeated on every child row.

## Final Schema Direction

The coordinated migration should:

- perform the accepted table and column renames;
- add `optimization_trials`;
- add `research_artifacts` and a run-to-artifact relationship table;
- add purpose, manifest, engine/build, structured warning, provenance, and reproducibility fields
  to `backtest_runs`;
- evolve experiments with methodology, training policy, window lengths, embargo/lag policy,
  optimizer/objective versions, frozen search space, lifecycle, failure details, timestamps, and a
  final-holdout run relationship;
- evolve windows with train/test boundaries, status, OOS run ownership, and selection information;
- enforce one candidate index and candidate hash per window and at most one selected trial through
  a partial unique index;
- add composite run/date, experiment/window, purpose/latest-evidence, and artifact-hash indexes;
- add safe numeric, state, purpose, and chronological checks;
- remove copied window/experiment aggregates and the redundant existing group/window index.

Legacy memberships backfill as completed `rolling_test` experiments. Their runs become
`rolling_window`; other legacy runs become `standalone`. Missing historical inputs must be labeled
`legacy_incomplete`, not populated with placeholders that imply reproducibility.

The downgrade recreates the legacy names and fields. Optimization-only data may be discarded on
downgrade and that loss must be called out by migration validation and rollback documentation.

## Walk-Forward Decisions

The completed optimizer follows these decisions. Detailed calculations and leakage rules live in
the [Walk-Forward Optimization Plan](walk-forward-optimization-plan.md).

| Decision | Accepted behavior |
|---|---|
| Training policies | Support both rolling and expanding training windows. |
| Default windows | 12 training months, 1-month OOS windows, 1-month steps. |
| Final holdout | Reserve an untouched final 6-month period. |
| Overlap | Require `step_months >= test_months`; do not stitch overlapping OOS periods. |
| Optimizers | Pluggable optimizer interface with exhaustive grid and seeded random search. |
| Trial storage | Persist summaries, parameters, metrics, provenance, and diagnostics; full outputs only for selected OOS and holdout runs. |
| Objective | Versioned `calmar_v1` with promotion-aligned eligibility gates. |
| Data lag | Source-aware availability policy; zero embargo is allowed only for price-only prior-day signals. |
| Failure policy | Fail fast, preserve structured experiment diagnostics, and start a new experiment for retry. |
| Operator surfaces | Shared services and CLI are required; web parity and a runtime job are separate work. |

`calmar_v1` admits a candidate only when it has at least 10 executions, 126 scored sessions,
positive annualized return, maximum drawdown no worse than -25%, and no fatal data-quality warning.
Its score is annualized return divided by `max(abs(max_drawdown), 1 percentage point)`. Ties resolve
by annualized return, lower drawdown, execution count, then canonical candidate order.

## Implementation Phases

### Phase 1: Atomic persistence

- Change participating backtest writes to `commit_unit_of_work`.
- Wrap all run result writes in a post-I/O `unit_of_work`.
- Add failure injection at the header, execution, snapshot, and finalization boundaries.

Developer verification: every injected failure leaves all research result tables unchanged.

### Phase 2: Contracts and schema

- Add passive contracts for run purposes, manifests, artifacts, experiments, windows, trials,
  objectives, optimizers, and reports.
- Implement the coordinated migration and cut repositories over in the same phase.
- Preserve legacy rows with honest methodology and reproducibility labels.

Developer verification: the schema description shows unambiguous ownership, constraints, and
legacy classifications.

### Phase 3: Immutable simulation inputs

- Add immutable validated parameter overrides without mutating `strategies.params_json`.
- Snapshot effective configuration and input artifacts before persistence.
- Add offline replay and hash/deduplication behavior.

Developer verification: disabling the market-data provider still permits an identical replay from
the stored manifest and artifacts.

### Phase 4: Training and selection

- Build leakage-safe rolling and expanding windows.
- Implement grid and seeded-random candidate generation behind one optimizer contract.
- Persist every attempted candidate summary and apply `calmar_v1` deterministically.
- Freeze the selected parameters before OOS execution.

Developer verification: a fixed changing-regime fixture selects the expected candidate using
training data only.

### Phase 5: OOS and holdout execution

- Execute one complete atomic OOS run for each selected window.
- Produce window-distribution and chain-linked, non-overlapping OOS metrics.
- Run the untouched holdout after every OOS window completes.
- On failure, roll back the active result tree, mark the experiment failed, and stop.

Developer verification: every OOS and holdout result traces to immutable parameters, inputs, and a
prior training selection.

### Phase 6: Evidence consumers and operations

- Make latest-run, leaderboard, evaluation, and promotion queries purpose-aware.
- Require a completed reproducible optimization experiment, passing OOS evidence, and a passing
  untouched holdout before the new evidence satisfies research promotion.
- Keep legacy rolling tests reportable without treating them as full optimization.
- Add CLI creation, status, failure inspection, and detailed reporting over shared services.

Developer verification: a CLI report traces promotion evidence through the experiment, windows,
selected trials, OOS runs, holdout, manifests, and artifacts.

## Validation and Completion Criteria

Minimum validation includes:

- migration upgrade/downgrade and legacy backfill;
- rollback at every backtest persistence boundary;
- purpose-aware query and repository constraints;
- manifest canonicalization, artifact deduplication, missing-artifact handling, and offline replay;
- rolling/expanding boundaries, warm-up, source lag, holdout exclusion, and overlap rejection;
- deterministic grid/random generation, objective eligibility, and tie-breaking;
- proof that OOS and holdout observations never enter training selection;
- fail-fast experiment state with no partial backtest tree;
- reconciliation of reports against authoritative executions and snapshots;
- exclusion of failed, legacy-incomplete, training, or purpose-ineligible evidence from promotion.

The program is complete when all six phases pass their focused tests and the full repository checks,
the documentation describes implemented behavior rather than intent, and full optimization can be
operated through the CLI and shared services. Web parity, scheduled execution, resumability,
Bayesian optimization, and automatic artifact pruning are not part of this completion boundary.

## Progress Tracker

| Phase | State | Next deliverable |
|---|---|---|
| Documentation baseline | Complete | Accepted plan and methodology responsibilities are reconciled. |
| Atomic persistence | Pending | Post-I/O unit-of-work implementation and failure-injection tests. |
| Contracts and final schema | Pending | Typed contracts, coordinated migration, and repository cutover. |
| Immutable simulation inputs | Pending | Manifest/artifact storage and offline replay. |
| Training and selection | Pending | Optimizer interface, grid/random search, and `calmar_v1`. |
| OOS and final holdout | Pending | Atomic OOS/holdout execution and aggregation. |
| Evidence consumers and CLI | Pending | Purpose-aware reporting, evaluation, promotion, and CLI operations. |

## Boundaries

- Do not implement migrations table by table when ownership depends on the final cross-table model.
- Do not retain failed or partial backtest output trees.
- Do not claim exact reproducibility from manifests or hashes unless immutable input payloads remain
  available.
- Do not let training, rolling-window, failed, or incomplete runs silently enter standalone or
  promotion evidence.
- Do not call the current rolling-window workflow full walk-forward optimization.
- Do not blend training metrics into reported OOS or holdout performance.
- Do not mutate canonical strategy parameters during optimization.

## Related Docs

- [Backtesting reference](backtesting.md)
- [Walk-forward optimization plan](walk-forward-optimization-plan.md)
- [Database transactions](database-transactions.md)
- [Database schema](db-schema.md)
- [Database diagram decisions](database-diagram-decisions.md)
- [Architecture conventions](../architecture/architecture-conventions.md)
