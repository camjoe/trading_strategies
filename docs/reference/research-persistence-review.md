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

The five reviewed research tables held no rows in the live database on 2026-07-21 and are expected to
remain empty. Any rows that might exist carry no methodology, purpose, or reproducibility metadata
worth preserving, so the coordinated migration drops and recreates these tables instead of carrying
legacy rows forward. There is no backfill, no `legacy_incomplete` labeling, and no legacy-data-loss
surface to document on downgrade.

## Delivery Strategy

Do not implement this table by table. Table-level changes are coupled by run purpose, provenance,
experiment ownership, evidence queries, and deletion behavior. Also do not hold every improvement
until the full optimizer is ready.

Use this sequence:

1. Make completed backtest persistence atomic without changing the schema.
2. Freeze the end-state contracts across runs, experiments, windows, and trials.
3. Apply one coordinated schema migration and repository cutover.
4. Add immutable inputs and parameterized simulation.
5. Implement training, selection, OOS execution, and final holdout as vertical workflows.
6. Cut reports, evaluation, promotion, and CLI operations over to the new evidence model.

These six steps form two separately committed programs:

- **Program A — schema in good shape (steps 1–3):** atomicity, frozen contracts, and the one
  coordinated migration + repository cutover, including purpose-aware read queries. This delivers the
  original "backtest and walk-forward tables in good shape" goal and can ship and be declared done on
  its own.
- **Program B — walk-forward optimizer (steps 4–6):** immutable inputs, training/selection, OOS and
  holdout execution, and evidence-aware consumers. This is a separate commitment built on Program A.

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
- manifest schema version.

The manifest is a **provenance and audit record**, not a replay input. It captures enough to explain
and trust what a run consumed; it is not a guarantee that the run can be re-executed offline from
stored bytes. **Offline replay and input-payload storage are both out of scope.**

The plan does not persist full input *payloads*: there is no content-addressed artifact store, no
canonical-JSON hashing, no deduplication, and no `research_artifacts` table. Provider/source and
as-of metadata on the manifest are the record of what a run consumed. One accepted consequence is
that a later rerun may differ slightly if the data provider has revised history; that is a trade-off
for this workflow, not a defect. Point-in-time *validity* — ensuring a run never used information
unavailable at the simulated decision time — is a separate concern handled by the availability-lag
and as-of controls in the
[Walk-Forward Optimization Plan](walk-forward-optimization-plan.md#provenance-and-leakage-controls),
which need only metadata, not stored payloads.

A run is eligible for promotion only when its manifest is complete.

### Metric ownership

- Executions and equity snapshots are authoritative run outputs.
- Window return and experiment aggregate fields are derived from their OOS runs rather than copied
  into multiple tables.
- Trial metrics remain persisted because they are the evidence used to rank candidates.
- Metric and objective versions live at the owning run, trial, or experiment boundary rather than
  being repeated on every child row.

## Final Schema Direction

The coordinated migration should:

- drop and recreate the five research tables rather than carrying legacy rows forward (see
  [Current State](#current-state)); no backfill and no `legacy_incomplete` labeling;
- apply the accepted table and column renames as part of that recreation;
- add a required `purpose` discriminator to `backtest_runs`, constrained by
  `CHECK (purpose IN ('standalone', 'rolling_window', 'walk_forward_oos', 'final_holdout'))`;
- add manifest, engine/build, structured warning, and provenance fields to `backtest_runs`;
- add `optimization_trials`;
- evolve experiments with methodology, training policy, window lengths, embargo/lag policy,
  optimizer/objective versions, frozen search space, lifecycle, failure details, timestamps, and a
  final-holdout run relationship;
- evolve windows with train/test boundaries, status, OOS run ownership, and selection information;
- enforce one candidate index and candidate hash per window and at most one selected trial through
  a partial unique index;
- add composite run/date, experiment/window, and purpose/latest-evidence indexes;
- add safe numeric, state, purpose, and chronological checks;
- remove copied window/experiment aggregates and the redundant existing group/window index.

A `research_artifacts` table, a run-to-artifact relationship table, and an artifact-hash index are
**not part of this plan** (see
[Run manifests and immutable artifacts](#run-manifests-and-immutable-artifacts)): the manifest carries
provider/as-of metadata instead of stored input payloads.

Because the tables are recreated empty, there is no forward backfill and no reproducibility labeling.
The downgrade simply recreates the prior table shapes; since no research rows are preserved in either
direction, there is no data-loss surface to document beyond the empty-table note.

## Walk-Forward Decisions

The completed optimizer follows these decisions. Detailed calculations and leakage rules live in
the [Walk-Forward Optimization Plan](walk-forward-optimization-plan.md).

| Decision | Accepted behavior |
|---|---|
| Training policies | Single rolling training policy for now; expanding is deferred future work. |
| Default windows | 12 training months, 1-month OOS windows, 1-month steps. |
| Final holdout | Reserve an untouched final 6-month period. |
| Overlap | Require `step_months >= test_months`; do not stitch overlapping OOS periods. |
| Optimizers | Exhaustive deterministic grid search only; seeded random and a pluggable interface are deferred future work. |
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

- Add passive contracts for run purposes, manifests, experiments, windows, trials, objectives,
  optimizers, and reports.
- Implement the coordinated drop-and-recreate migration and cut repositories over in the same phase.
- Make existing read queries (latest-run, leaderboard, evaluation) purpose-aware as soon as the
  discriminator exists, so no consumer silently mixes evidence purposes. (Promotion gating stays in
  Phase 6, where OOS and holdout evidence exist.)
- Preserve the `tradeCount` transport alias and assert it in the contract tests so the web client
  does not break.

Developer verification: the schema description shows unambiguous ownership, constraints, and the
`purpose` enumeration; a latest-run query for one purpose never returns another purpose's rows.

### Phase 3: Immutable simulation inputs

- Add immutable validated parameter overrides without mutating `strategies.params_json`.
- Resolve and freeze the effective configuration manifest (provenance and audit) before persistence.
- **Offline replay and input-payload storage are out of scope.** Persist provider/source and as-of
  metadata on the manifest instead of full input payloads — no content-addressed store, hashing, or
  deduplication (see
  [Run manifests and immutable artifacts](#run-manifests-and-immutable-artifacts)).

Developer verification: a persisted run resolves to a complete, human-auditable manifest (validated
parameters, configuration, universe lineage, provider/as-of metadata, and engine/build provenance)
without mutating any canonical strategy parameters.

### Phase 4: Training and selection

- Build leakage-safe rolling training windows. (Expanding is deferred future work.)
- Implement deterministic grid candidate generation. (Seeded random and a pluggable optimizer
  interface are deferred future work.)
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

- Make promotion queries purpose-aware and gate on the new evidence model. (Latest-run, leaderboard,
  and evaluation queries were already made purpose-aware in Phase 2.)
- Require a completed optimization experiment, passing OOS evidence, and a passing untouched holdout
  before the new evidence satisfies research promotion.
- Keep rolling-window tests reportable without treating them as full optimization.
- Add CLI creation, status, failure inspection, and detailed reporting over shared services.

Developer verification: a CLI report traces promotion evidence through the experiment, windows,
selected trials, OOS runs, holdout, and manifests.

## Validation and Completion Criteria

Minimum validation includes:

- migration upgrade/downgrade on empty tables (drop-and-recreate; no backfill);
- rollback at every backtest persistence boundary;
- purpose-aware query and repository constraints;
- manifest canonicalization and completeness (no artifact-payload/dedup or offline-replay validation);
- rolling training-window boundaries, warm-up, source lag, holdout exclusion, and overlap rejection;
- deterministic grid generation, objective eligibility, and tie-breaking;
- proof that OOS and holdout observations never enter training selection;
- fail-fast experiment state with no partial backtest tree;
- reconciliation of reports against authoritative executions and snapshots;
- exclusion of failed, training, or purpose-ineligible evidence from promotion.

The program is complete when all six phases pass their focused tests and the full repository checks,
the documentation describes implemented behavior rather than intent, and full optimization can be
operated through the CLI and shared services. Expanding training windows, seeded random search, a
pluggable optimizer interface, offline replay, input-payload artifact storage, web parity, scheduled
execution, resumability, Bayesian optimization, and automatic artifact pruning are not part of this
completion boundary.

## Progress Tracker

The six phases form two separately committed programs (see [Delivery Strategy](#delivery-strategy)).

**Program A — schema in good shape**

| Phase | State | Next deliverable |
|---|---|---|
| Documentation baseline | Complete | Accepted plan and methodology responsibilities are reconciled. |
| Atomic persistence | Pending | Post-I/O unit-of-work implementation and failure-injection tests. |
| Contracts and final schema | Pending | Typed contracts, drop-and-recreate migration, repository cutover, and purpose-aware read queries. |

**Program B — walk-forward optimizer**

| Phase | State | Next deliverable |
|---|---|---|
| Immutable simulation inputs | Pending | Manifest resolution and immutable parameter overrides (no input-payload store). |
| Training and selection | Pending | Grid search and `calmar_v1` (single rolling policy; random/pluggable/expanding deferred). |
| OOS and final holdout | Pending | Atomic OOS/holdout execution and aggregation. |
| Evidence consumers and CLI | Pending | Purpose-aware promotion, evidence reporting, and CLI operations. |

## Boundaries

- Do not implement migrations table by table when ownership depends on the final cross-table model.
- Do not retain failed or partial backtest output trees.
- Do not claim a run can be re-executed offline; the manifest is a provenance and audit record, not a
  replay guarantee.
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
