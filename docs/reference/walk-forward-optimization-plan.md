# Program B — Walk-Forward Optimizer Plan

Type: notes
Status: Active
Created: 2026-07-17
Last Reviewed: 2026-07-21
Purpose: Own the methodology, leakage controls, schema, delivery phases, and completion criteria for evolving rolling-window tests into full train-optimize-test walk-forward optimization.
Related: [Program A — Backtest and Walk-Forward Schema Plan](research-persistence-review.md), [Backtesting](backtesting.md), [Database Transactions](database-transactions.md), [Database Schema](db-schema.md), [Database Diagram Decisions](database-diagram-decisions.md)

## Purpose

This is the canonical plan for **Program B — the walk-forward optimizer**: the financial methodology,
leakage controls, optimizer schema, delivery phases, and evaluation-honesty requirements for full
train-optimize-test walk-forward optimization.

It is a plan until its completion criteria are implemented. It must not be read as a claim that the
current workflow already performs optimization.

**Prerequisite.** Program B builds on [Program A](research-persistence-review.md) — the renamed tables
(`walk_forward_experiments`, `walk_forward_windows`, `backtest_executions`), the
`backtest_runs.purpose` discriminator, and atomic persistence. Program A must be merged before Program B
begins; Program B adds its own numbered migration on top of Program A's schema.

## Current Capability

The current workflow executes a fixed strategy across chronologically shifted test windows. It stores
each simulation as a normal backtest and groups the window results.

This is **rolling-window robustness testing**. It is useful evidence, but it is not full walk-forward
optimization because it has no earlier training interval, candidate trials, predeclared selection
objective, frozen winner, or untouched final holdout.

## Target Lifecycle

For each chronological window:

1. Construct a training interval containing only information available before the test interval.
2. Generate a bounded candidate set from the experiment's frozen search space.
3. Evaluate candidates with identical data, universe, benchmark, fee, slippage, and execution
   assumptions.
4. Reject ineligible candidates and rank the remainder with the experiment's versioned objective.
5. Freeze the winner before observing the test interval.
6. Execute the selected parameters once over the unseen OOS interval.
7. Advance chronologically without allowing later observations to revise earlier selections.
8. After all OOS windows complete, evaluate the resulting process on an untouched final holdout.
9. Report training selection, OOS evidence, and holdout evidence separately.

The existing daily-bar simulator remains the execution engine. Optimization adds orchestration,
immutable parameter injection, trial summaries, provenance manifests, and evidence-aware reporting.

## Window Methodology

### Training policies

Use a single training policy for now:

- **Rolling (current):** use the fixed-length interval immediately preceding each test window.

**Expanding training windows** (a fixed inception date extended through the date before each test
window) are **deferred future work.** Persist the policy name with the experiment so an expanding policy
can be added later without a schema change.

Production defaults are 12 training months, 1-month test windows, 1-month steps, and a final untouched
6-month holdout. These values remain configurable and must be persisted.

Each window persists `train_start`, `train_end`, `test_start`, and `test_end`. Training must end before
testing starts. The final holdout is excluded from every training and OOS interval.

### Warm-up and source availability

Indicator warm-up observations may precede a scoring interval, but they are used only to initialize
calculations. They do not count toward objective metrics or eligibility sample sizes. Persist the
warm-up policy with the experiment and run manifests.

Price-only daily strategies may use zero embargo because signals use prior-day values and execute on the
next bar. External features must declare their point-in-time availability or publication lag. Apply that
lag during construction and persist it with the source provenance. An explicit positive embargo remains
available when a source requires additional separation.

An embargo is not a substitute for point-in-time data. Revised external data is eligible only when the
recorded provider/as-of metadata represents what would have been available at the simulated decision
time.

### OOS overlap

Require `step_months >= test_months`. Reject overlapping OOS windows rather than silently
double-counting dates in stitched results. Steps longer than test windows may create labeled gaps;
reports must not imply continuous exposure across those gaps.

## Candidate Search

Candidate parameters come from an explicit, bounded search-space snapshot compatible with the strategy
primitive's existing validation schema. Optimization must never mutate `strategies.params_json`; the
simulator receives an immutable validated override.

Use a single optimizer for now:

- **exhaustive deterministic grid search.**

Every experiment persists optimizer name/version, canonical search-space snapshot, and candidate budget.
Candidate ordering and canonical parameter serialization must be deterministic. Reject a grid whose
Cartesian product exceeds the explicit candidate budget rather than truncating it invisibly.

**Seeded random search and a pluggable optimizer interface are deferred future work.** Persist the
optimizer name/version (and a seed field, unused by grid) so a second optimizer can be added later
without a schema change. Bayesian or adaptive search is also out of scope; a future optimizer must
persist all model state, search history, stopping rules, and seeds needed to explain its choices.

## Objective and Eligibility

The initial objective is `calmar_v1`. It is selected before execution and applied identically to every
candidate and window.

A training candidate is eligible only when it has:

- at least 10 simulated executions;
- at least 126 scored equity sessions;
- positive annualized return;
- maximum drawdown no worse than -25%;
- no fatal data-quality warning.

The score is:

```text
annualized_return_pct / max(abs(max_drawdown_pct), 1.0)
```

The one-percentage-point denominator floor makes the zero-drawdown case finite and persistable. Rank
higher scores first. Deterministic ties resolve by:

1. higher annualized return;
2. lower absolute drawdown;
3. higher execution count;
4. canonical candidate order.

Persist the objective name/version, value, component metrics, eligibility, rejection reasons, and
tie-break fields for every candidate. If no candidate is eligible, fail the experiment; never select the
least-bad ineligible candidate.

Test and holdout results are evaluation outputs only. They must never influence candidate ranking or
cause an earlier winner to be replaced.

## Run Manifests

`book_strategy_history` and `book_universe_history` remain useful lineage sources, but they cannot
reproduce a run by themselves. At execution time, resolve effective state and freeze it into a versioned
run manifest.

The manifest includes:

- strategy identity and exact validated parameters;
- effective account/book settings that affect simulation;
- initial cash, benchmark, dates, fees, slippage, warm-up, and execution policies;
- exact universe membership and its source lineage;
- market and external-feature provider/as-of metadata;
- engine version, application build, source revision, and dirty-state provenance;
- manifest schema version.

The manifest is a **provenance and audit record**, not a replay input. It captures enough to explain and
trust what a run consumed; it is not a guarantee that the run can be re-executed offline from stored
bytes. **Offline replay and input-payload storage are both out of scope.**

The plan does not persist full input *payloads*: there is no content-addressed artifact store, no
canonical-JSON hashing, no deduplication, and no `research_artifacts` table. Provider/source and as-of
metadata on the manifest are the record of what a run consumed. One accepted consequence is that a later
rerun may differ slightly if the data provider has revised history; that is a trade-off for this
workflow, not a defect. Point-in-time *validity* — ensuring a run never used information unavailable at
the simulated decision time — is handled by the availability-lag and as-of controls in
[Provenance and Leakage Controls](#provenance-and-leakage-controls), which need only metadata.

Optimization injects an immutable validated parameter override into the simulator and never mutates
`strategies.params_json`. A run is eligible for promotion only when its manifest is complete.

## Persistence and Failure Semantics

Persist trial summaries rather than full training result trees. Each trial records:

- canonical parameters and hash;
- candidate and optimizer sequence;
- objective components and value;
- eligibility and structured rejection reasons;
- execution status, warnings, duration, and reproducibility provenance;
- whether it was selected.

Full executions and equity snapshots are reserved for selected OOS and final-holdout runs.
`walk_forward_experiments` / `walk_forward_windows` own membership; shared `backtest_runs` rows own
complete simulator results. The table ownership and migration are specified in
[Program B Schema and Migration](#program-b-schema-and-migration).

The workflow is fail-fast:

- roll back the active trial or complete backtest unit;
- persist structured failure diagnostics on the trial/window and experiment boundary;
- stop the experiment immediately;
- retry by creating a new experiment rather than resuming or mutating the failed experiment.

Failed experiment metadata is audit evidence. Partial backtest executions or equity trees are not.

## OOS and Holdout Evaluation

After candidate selection, freeze the selected parameters and manifest before the OOS interval begins.
Execute each OOS period exactly once for that experiment.

Report two OOS views:

- a window distribution containing return, drawdown, execution count, dispersion, and diagnostics;
- a chain-linked chronological series assembled from non-overlapping OOS periods.

Do not sum or directly concatenate independently reset account equity values. Chain-link returns and
label any gaps introduced by a step longer than the test interval.

After all OOS windows complete, run the selected process over the untouched 6-month holdout. The holdout
is required before this new optimization evidence can satisfy research promotion. Promotion uses
completed OOS and holdout evidence and the configured promotion gates; it does not use training
performance as realized evidence.

Rolling-window experiments remain reportable but do not satisfy the full optimization requirement.

## Provenance and Leakage Controls

Every candidate, OOS run, and holdout must resolve to an immutable, auditable record of its effective
inputs:

- validated strategy parameters;
- initial capital, benchmark, fees, slippage, execution, and warm-up configuration;
- exact universe membership;
- market and feature data provider and as-of metadata (full input-payload storage and offline replay
  are out of scope; see [Run Manifests](#run-manifests));
- engine/objective/optimizer versions and source/build provenance.

Required controls:

| Risk | Control |
|---|---|
| Look-ahead | Enforce boundaries in pure domain logic and prove ranking sees training results only. |
| External-data revision | Record point-in-time availability lags and provider/as-of metadata so revisions are detectable, and apply the lag during construction. |
| Parameter overfitting | Bound and disclose the search space, candidate count, OOS sequence, and untouched holdout. |
| Multiple testing | Persist every attempted candidate summary rather than only the winner. |
| Regime specialization | Compare window stability and chain-linked OOS behavior, not only an aggregate return. |
| Inconsistent assumptions | Freeze one input manifest and configuration for comparable candidates. |
| Misleading reporting | Label training, OOS, and holdout metrics separately and never blend them. |

## Program B Schema and Migration

Program B adds its own numbered migration on top of Program A's renamed tables. It should:

- add manifest, engine/build, structured warning, and provenance fields to `backtest_runs`;
- add `optimization_trials` (per-candidate summaries: canonical parameters and hash, candidate/optimizer
  sequence, objective components and value, eligibility and rejection reasons, status/warnings/duration,
  provenance, and a selected flag);
- evolve `walk_forward_experiments` with methodology, training policy, window lengths, embargo/lag
  policy, optimizer/objective versions, frozen search space, candidate budget, lifecycle, failure
  details, timestamps, and a final-holdout run relationship;
- evolve `walk_forward_windows` with train/test boundaries (`train_start`, `train_end`, `test_start`,
  `test_end`), status, OOS run ownership, and selection information;
- enforce one candidate index and candidate hash per window and at most one selected trial per window
  through partial unique indexes;
- add composite run/date, experiment/window, and purpose/latest-evidence indexes;
- add safe numeric, state, and chronological checks (training ends before testing; non-overlapping OOS).

A `research_artifacts` table, a run-to-artifact relationship table, and an artifact-hash index are **not
part of this plan** (see [Run Manifests](#run-manifests)): the manifest carries provider/as-of metadata
instead of stored input payloads.

## Architecture Alignment

Follow the existing dependency direction:

- `backtesting/domain/`: pure boundaries, search generation, objective calculation, eligibility,
  ranking, tie-breaks, chain-linking, and leakage validation;
- `backtesting/models/`: passive configuration, manifest, experiment, trial, selection, and report
  contracts;
- `backtesting/repositories/`: SQL persistence and purpose-aware evidence queries;
- `backtesting/services/`: data resolution, orchestration, atomic execution, failure recording, and
  reporting;
- `interfaces/cli/`: operator inputs and output over the shared services.

Infrastructure owns the concrete market-data adapter. Domain and service code must not import that
implementation directly.

Expanding training windows, seeded random search, a pluggable optimizer interface, offline replay,
input-payload artifact storage, web parity, a scheduled runtime job, resumability, Bayesian
optimization, and automatic artifact pruning are separate work and do not block the accepted
CLI/service completion boundary.

## Implementation Phases

Program B begins after [Program A](research-persistence-review.md) merges.

### Phase B1: Immutable simulation inputs

- Add immutable validated parameter overrides without mutating `strategies.params_json`.
- Resolve and freeze the effective configuration manifest (provenance and audit) before persistence.
- **Offline replay and input-payload storage are out of scope.** Persist provider/source and as-of
  metadata on the manifest instead of full input payloads — no content-addressed store, hashing, or
  deduplication (see [Run Manifests](#run-manifests)).
- Land the migration described in [Program B Schema and Migration](#program-b-schema-and-migration).

Developer verification: a persisted run resolves to a complete, human-auditable manifest (validated
parameters, configuration, universe lineage, provider/as-of metadata, and engine/build provenance)
without mutating any canonical strategy parameters.

### Phase B2: Training and selection

- Build leakage-safe rolling training windows. (Expanding is deferred future work.)
- Implement deterministic grid candidate generation. (Seeded random and a pluggable optimizer interface
  are deferred future work.)
- Persist every attempted candidate summary and apply `calmar_v1` deterministically.
- Freeze the selected parameters before OOS execution.

Developer verification: a fixed changing-regime fixture selects the expected candidate using training
data only.

### Phase B3: OOS and holdout execution

- Execute one complete atomic OOS run for each selected window.
- Produce window-distribution and chain-linked, non-overlapping OOS metrics.
- Run the untouched holdout after every OOS window completes.
- On failure, roll back the active result tree, mark the experiment failed, and stop.

Developer verification: every OOS and holdout result traces to immutable parameters, inputs, and a prior
training selection.

### Phase B4: Evidence consumers and operations

- Make promotion queries purpose-aware and gate on the new evidence model. (Latest-run, leaderboard, and
  evaluation queries were already made purpose-aware in Program A.)
- Require a completed optimization experiment, passing OOS evidence, and a passing untouched holdout
  before the new evidence satisfies research promotion.
- Keep rolling-window tests reportable without treating them as full optimization.
- Add CLI creation, status, failure inspection, and detailed reporting over shared services.

Developer verification: a CLI report traces promotion evidence through the experiment, windows, selected
trials, OOS runs, holdout, and manifests.

## Validation Strategy

Automated coverage must include:

- exact rolling training-window boundaries;
- warm-up exclusion and source-specific availability lags;
- final-holdout isolation and OOS overlap rejection;
- deterministic grid candidate generation;
- parameter validation without catalog mutation;
- objective eligibility, denominator floor, rejection, and tie-breaking;
- proof that ranking receives training data only;
- consistent assumptions and a frozen input manifest across candidates;
- atomic OOS and holdout persistence;
- fail-fast experiment state without partial backtest trees;
- chain-linked OOS aggregation without duplicate dates;
- reports that keep training, OOS, and holdout evidence distinct;
- promotion exclusion for failed, incomplete, or purpose-ineligible evidence.

Include a deterministic changing-regime fixture whose expected winners and OOS results are fixed by
construction rather than incidental live market data.

## Completion Criteria

The capability may be called full train-optimize-test walk-forward optimization only when:

- every OOS window has an earlier persisted training interval;
- all attempted candidates and outcomes are auditable;
- selection uses only a predetermined versioned objective and training evidence;
- selected parameters are frozen before OOS execution;
- manifests capture provenance (validated parameters, configuration, universe lineage, provider/as-of
  metadata, and engine/build) for audit;
- chronological leakage checks pass for prices, features, universes, and benchmarks;
- OOS windows are non-overlapping and aggregated honestly;
- an untouched final holdout is executed after OOS completion;
- reports and promotion keep training, OOS, and holdout evidence distinct;
- rolling-window tests remain correctly identified;
- shared services and CLI operation work without requiring the web UI.

Program A (schema hygiene and atomic persistence) is tracked separately in
[Program A — Backtest and Walk-Forward Schema Plan](research-persistence-review.md).

## Progress Tracker

Program B begins after [Program A](research-persistence-review.md) merges.

| Phase | State | Next deliverable |
|---|---|---|
| B1 — Immutable simulation inputs | Pending | Program B migration, manifest resolution, and immutable parameter overrides (no input-payload store). |
| B2 — Training and selection | Pending | Grid search and `calmar_v1` (single rolling policy; random/pluggable/expanding deferred). |
| B3 — OOS and final holdout | Pending | Atomic OOS/holdout execution and aggregation. |
| B4 — Evidence consumers and CLI | Pending | Purpose-aware promotion, evidence reporting, and CLI operations. |

## Boundaries

- Do not claim a run can be re-executed offline; the manifest is a provenance and audit record, not a
  replay guarantee.
- Do not let training, failed, or incomplete runs silently enter standalone or promotion evidence.
- Do not blend training metrics into reported OOS or holdout performance.
- Do not mutate canonical strategy parameters during optimization.
- Do not add expanding windows, seeded random search, a pluggable optimizer interface, offline replay,
  or an input-payload store within this completion boundary.

## Related Docs

- [Program A — Backtest and Walk-Forward Schema Plan](research-persistence-review.md)
- [Backtesting reference](backtesting.md)
- [Database transactions](database-transactions.md)
- [Database schema](db-schema.md)
- [Database diagram and terminology decisions](database-diagram-decisions.md)
- [Architecture conventions](../architecture/architecture-conventions.md)
