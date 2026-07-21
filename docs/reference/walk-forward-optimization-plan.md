# Walk-Forward Optimization Plan

Type: notes
Status: Draft
Created: 2026-07-17
Last Reviewed: 2026-07-17
Purpose: Plan a leakage-safe evolution from rolling-window robustness tests to a full train-optimize-test walk-forward optimization system.
Related: [Backtesting](backtesting.md), [Database Diagram Decisions](database-diagram-decisions.md), [Database Schema](db-schema.md), [DB Schema Review](../db-schema-review.md)

## Purpose

This document defines the intended methodology, persistence model, implementation phases, and verification criteria for full walk-forward optimization. It is a planning artifact, not a claim that the described capability exists today.

## Current Capability

The current workflow creates chronologically shifted test windows. Each window runs through the normal backtest simulator and is stored as a `backtest_runs` row with its usual trades and equity snapshots. `walk_forward_group_runs` records window membership and return, while `walk_forward_groups` records window settings and aggregate results.

This is appropriately described as **rolling-window robustness testing**. It tests a fixed strategy across multiple periods, but it does not persist or perform the complete train-optimize-test lifecycle because it has no separate training windows, parameter trials, selection objective, or per-window frozen parameter snapshot.

## Target Outcome

For every chronological window, the system should:

1. Build a training interval containing only data available before the test interval.
2. Generate a bounded, explicit set of candidate strategy parameter configurations.
3. Evaluate every candidate using the same training data, universe policy, benchmark, fees, slippage, and execution assumptions.
4. Rank candidates using a predetermined objective and deterministic tie-break rules.
5. Freeze the selected parameters before the test interval begins.
6. Run one out-of-sample backtest over the unseen test interval.
7. Advance chronologically and repeat without allowing later windows to affect earlier selection.
8. Report both per-window results and a stitched out-of-sample result across all test windows.

The existing backtest simulator remains the execution engine for candidate and out-of-sample runs. Walk-forward optimization adds experimental orchestration, parameter injection, persistence, and reporting.

## Methodology

### Window construction

Support two explicit training policies:

- **Rolling training window:** use a fixed-length interval immediately preceding each test window. This limits regime history and keeps training sample sizes comparable.
- **Expanding training window:** start from a fixed inception date and extend training through the date immediately before each test window. This uses all historical information that would have been available at that point.

Each window must persist `train_start`, `train_end`, `test_start`, and `test_end`. The training interval must end before the test interval begins. If indicators or features need warm-up history, fetch that history only to initialize calculations; exclude warm-up observations from objective scoring and persist the warm-up policy separately.

An optional embargo gap may be introduced between training and testing when feature construction, labels, or delayed external data could otherwise leak across the boundary. The gap must be a named configuration value, not an implicit date adjustment.

### Candidate parameter space

Candidate values must come from an explicit, bounded search-space definition compatible with each strategy primitive's knob schema. The initial implementation should use deterministic grid search because it is transparent, reproducible, and straightforward to test. Random, Bayesian, or adaptive search can be considered later only if the seed, search history, and stopping policy are persisted.

Every candidate must be validated through the existing strategy parameter validation path. Candidate evaluation must not mutate the canonical `strategies.params_json` row. Instead, the simulator should receive an immutable parameter override for that run.

### Optimization objective

The objective must be chosen before any window runs and applied consistently across all candidates and windows. It should not default silently from whichever metric happens to be available.

A recommended initial objective is a risk-adjusted training score with explicit penalties or eligibility floors for inadequate sample size, excessive drawdown, and insufficient trade count. The exact formula and thresholds remain a domain decision and must be named constants at the owning domain layer before implementation.

Persist:

- objective name and version;
- objective value for every candidate;
- component metrics used by the objective;
- eligibility or rejection reasons;
- deterministic tie-break fields and the selected candidate.

Do not choose a candidate using its test-window result. Test results are evaluation outputs only.

### Out-of-sample execution

After selection, copy the chosen candidate parameters into an immutable snapshot attached to the window's out-of-sample run. Execute the test window once using that snapshot. The test run may reuse `backtest_runs`, `backtest_trades`, and `backtest_equity_snapshots`, but it must be distinguishable from standalone and training runs.

When test windows overlap because `step_months` is shorter than `test_months`, a stitched equity series would double-count dates. Full optimization should therefore either reject overlapping out-of-sample windows initially or define and persist an explicit overlap policy before producing stitched results. The recommended first version requires non-overlapping test windows.

### Aggregate reporting

Report two complementary views:

- **Window distribution:** average, median, best, worst, dispersion, drawdown, trade count, and pass/fail diagnostics across test windows.
- **Stitched out-of-sample history:** one chronological equity and trade sequence assembled only from non-overlapping test periods.

Training performance must be visibly separated from out-of-sample performance. Promotion and strategy comparison surfaces should consume out-of-sample evidence and must not blend training scores into reported realized evaluation returns.

## Proposed Persistence Model

Use an additive migration where practical so existing rolling-window groups remain readable. Final names should be confirmed during migration design.

### `walk_forward_groups`

Retain the experiment-level row and add or otherwise persist:

- methodology mode (`rolling_test` or `train_optimize_test`);
- training policy (`rolling` or `expanding`);
- training length for rolling mode;
- test length and step length;
- embargo or gap policy;
- optimization objective name and version;
- parameter-space snapshot;
- simulator/configuration version;
- overlap policy;
- lifecycle status (`running`, `completed`, or `failed`);
- failure details and completion time.

### Walk-forward windows

Evolve `walk_forward_group_runs` or replace it with a clearly named window table that owns:

- group and window index;
- training and test date boundaries;
- selected trial identifier;
- out-of-sample `backtest_runs` identifier;
- frozen selected-parameter snapshot;
- selection reason and objective value;
- window status and failure details.

If a replacement table is chosen, migrate existing membership rows without pretending they have training artifacts; mark them as `rolling_test` windows.

The window→selected-trial relationship must not become a circular foreign key
(window references its winning trial while every trial references its window). The
2026-07-17 schema review recommends resolving this with the repository's existing
open-row idiom instead of a back-reference: a `selected` flag on the trial table
enforced by a partial unique index (`UNIQUE(window_id) WHERE selected = 1`), the
same pattern `book_strategy_assignments` and `book_universe_history` already use.

### Optimization trials

Add a trial table keyed by walk-forward window and candidate index. Each row should contain:

- validated parameter snapshot;
- candidate identity or deterministic hash;
- training-run reference or reproducible summary reference;
- objective value and component metrics;
- eligibility status and rejection reasons;
- execution status, warnings, and timing;
- selected flag.

Strategy-specific knobs may remain a validated JSON snapshot because their keys differ by primitive and canonical strategy knob values already use `params_json`. Experiment identity, dates, states, metric fields, and relationships should remain typed columns rather than becoming a generic entity-attribute-value model.

Storage recommendation (2026-07-17 review): persist trial *summaries* plus
reproducibility metadata (parameter hash, config snapshot, objective components) —
not full trades/equity series per trial. A modest experiment (30 candidates ×
8 windows) would otherwise persist 240 full backtest runs. Full trade/equity
persistence is reserved for the selected out-of-sample run, which promotion
evidence actually consumes; training trials remain reproducible from their
snapshots on demand.

### `backtest_runs`

Make every reused run self-describing by persisting:

- run purpose (`standalone`, `optimization_training`, or `walk_forward_oos`);
- effective strategy-parameter snapshot;
- effective backtest configuration snapshot;
- strategy primitive/config version;
- data/universe provenance sufficient for reproduction;
- optional parent window or trial relationship where that direction preserves clean ownership.

The migration design must avoid ambiguous or circular ownership. Walk-forward tables should own experiment membership; `backtest_runs` should remain a reusable simulation record.

## Schema Impact Summary (2026-07-17 review)

Concrete delta against the revision-0009 schema, from the table-by-table schema
review. All changes are additive or evolutionary — no existing data is invalidated,
and existing rolling-window groups remain readable as `rolling_test` experiments.

| Table | Change shape |
|---|---|
| `walk_forward_groups` | ~10 new columns: methodology mode, training policy + lengths, embargo policy, objective name/version, parameter-space snapshot, simulator version, overlap policy, lifecycle status + failure details. Existing rows backfill as `methodology_mode='rolling_test'`, `status='completed'`. |
| `walk_forward_group_runs` | Evolves into a windows table: adds nullable `train_start`/`train_end` (NULL for legacy rolling windows), frozen selected-parameter snapshot, selection reason, objective value, per-window status + failure details. |
| New trials table | One row per (window, candidate): parameter snapshot + hash, objective value + component metrics, eligibility/rejection reasons, execution status/warnings/timing, `selected` flag. `UNIQUE(window_id, candidate_index)`; selection enforced by partial unique index (see Walk-forward windows). |
| `backtest_runs` | `run_purpose` (`standalone` default), effective parameter snapshot, effective config snapshot, engine version, data/universe provenance. |

Expected migration footprint: one or two numbered revisions on the existing Alembic
chain; standard additive columns plus one table rebuild if `walk_forward_group_runs`
is renamed rather than extended.

## Effort Estimate (2026-07-17 review)

Assumes AI-assisted implementation sessions in this repository. The longest pole is
not code: Phase 1's domain decisions (objective formula, eligibility floors, minimum
training history per strategy horizon) must be settled by the operator before
implementation can be honest about what it optimizes.

| Phase | Estimate |
|---|---|
| 1 — Contracts and methodology decisions | 2–4 sessions (mostly decision time) |
| 2 — Parameterized simulation | 1–2 sessions |
| 3 — Schema and repositories | 1–2 sessions |
| 4 — Training and selection orchestration | 3–5 sessions (resumability and partial-failure semantics are the risk area) |
| 5 — Out-of-sample execution and aggregation | 2–3 sessions |
| 6 — Interfaces and governance integration | 2–3 sessions (more with a full web UI surface) |

Total: roughly 11–19 focused sessions — about 2–3 weeks full-time, 4–6 weeks at a
part-time cadence. Approximately a third of the effort is the validation strategy's
test coverage, which is not optional for a leakage-sensitive feature.

## Codebase Alignment

Follow the existing backtesting package layering:

- `backtesting/domain/`: pure window construction, candidate ranking, objective calculation, eligibility rules, tie-breaks, and leakage validations.
- `backtesting/models/`: passive configuration, window, trial, selection, and report contracts.
- `backtesting/repositories/`: SQL persistence and experiment/run queries.
- `backtesting/services/`: orchestration of training trials, selection, frozen out-of-sample execution, resumability, and reports.
- `interfaces/cli/` and runtime jobs: operator inputs, progress output, exit behavior, and scheduling.
- Web backend/frontend: optional transport and presentation over the same service APIs; never the sole control surface.

Refactor the simulator so a run can accept an explicit validated strategy-parameter snapshot without updating the catalog row. Preserve the existing prior-day signal and next-bar execution behavior.

## Implementation Phases

### Phase 1: Contracts and methodology decisions

- Choose rolling, expanding, or both training policies for the first release.
- Define permitted parameter spaces per strategy primitive.
- Approve the initial objective, eligibility floors, tie-breaks, and overlap policy.
- Add typed model contracts and pure domain tests for window boundaries, embargo handling, candidate ranking, and chronological isolation.

Developer verification: Given fixed dates and settings, inspect the generated train/test windows and confirm that each training end precedes its test start and no test data enters candidate ranking.

### Phase 2: Parameterized simulation

- Add an immutable parameter override to backtest execution.
- Snapshot effective parameters and run configuration on every run.
- Ensure strategy catalog rows are never mutated by optimization.
- Add equivalence tests showing that default parameter overrides reproduce the existing backtest result.

Developer verification: Run one strategy with two explicit parameter snapshots and confirm separate reproducible runs while `strategies.params_json` remains unchanged.

### Phase 3: Schema and repositories

- Create a reversible numbered migration for experiment, window, trial, and run provenance fields.
- Preserve existing rolling-window records as legacy/current-mode experiments.
- Add repository tests for uniqueness, ownership, cascade behavior, partial failure, and resume queries.

Developer verification: Use the schema description command to inspect all new relationships and verify that a window identifies its selected trial and out-of-sample run.

### Phase 4: Training and selection orchestration

- Execute the bounded candidate set for each training interval.
- Persist every trial before selecting the winner.
- Apply the versioned objective and deterministic tie-breaks.
- Persist selection before starting the out-of-sample run.
- Support fail-fast versus continue policies explicitly and make incomplete groups resumable.

Developer verification: Interrupt an experiment after a completed window, resume it, and confirm completed trials are not duplicated and the same winner is selected.

### Phase 5: Out-of-sample execution and aggregation

- Run each selected frozen configuration over its unseen test interval.
- Build window-distribution metrics and stitched out-of-sample results.
- Prevent overlapping windows from being silently double-counted.
- Keep training and test metrics separate in all report contracts.

Developer verification: Inspect a report and trace each out-of-sample result back to its prior training interval, trial set, selected parameters, and immutable run.

### Phase 6: Interfaces and governance integration

- Add CLI configuration for training policy, training length, test length, step, embargo, objective, and bounded parameter space.
- Add a detailed report showing training candidates, selection, and out-of-sample performance by window.
- Expose the same services to scheduled jobs and optionally the web UI.
- Decide how completed out-of-sample evidence contributes to promotion assessment; do not automatically enable live trading or rotation eligibility.

Developer verification: Run and report an experiment entirely through the CLI, then confirm any UI representation matches the same persisted service result.

## Validation Strategy

Minimum automated coverage should include:

- exact train/test boundary generation for rolling and expanding policies;
- rejection of non-chronological, overlapping, empty, or undersized windows according to policy;
- proof that objective calculation receives training results only;
- deterministic candidate selection and tie-breaking;
- immutable catalog parameters during optimization;
- parameter/config snapshots sufficient to reproduce a run;
- no look-ahead in signals, features, universes, benchmarks, or selection;
- consistent fees, slippage, benchmark, and universe handling across candidates;
- migration upgrade/downgrade and legacy rolling-group compatibility;
- transaction behavior for failed trials and resumable groups;
- stitched out-of-sample aggregation without duplicate dates;
- reporting that labels training and out-of-sample metrics distinctly.

Add an end-to-end deterministic fixture with deliberately changing regimes where different training windows select different candidates. Its expected selections and out-of-sample outputs should be fixed by construction rather than asserted from incidental market data.

## Risks and Controls

| Risk | Required control |
|---|---|
| Look-ahead leakage | Enforce chronological boundaries in domain logic and test them independently of interfaces. |
| Parameter overfitting | Bound the search space, apply minimum sample requirements, report trial count, and keep a final untouched holdout when making high-stakes comparisons. |
| Multiple-testing bias | Persist every attempted candidate and avoid reporting only the winner's training metric. |
| Regime over-specialization | Compare window stability and stitched out-of-sample behavior, not only aggregate return. |
| Inconsistent assumptions | Freeze fees, slippage, benchmark, universe, data version, and feature policy for all candidates in a group. |
| External-feature revisions | Persist provider/version/provenance and enforce as-of availability; never use data revised after the simulated decision time. |
| Compute and storage growth | Estimate candidate × window cost, bound trials, support resumability, and define retention without deleting audit evidence needed by promotion decisions. |
| Misleading reporting | Label all metrics as training or out-of-sample and never blend them into one performance number. |

## Open Decisions

- Which training policy ships first: rolling, expanding, or both?
- What minimum training history and test duration are valid for each strategy horizon?
- What objective and eligibility floors best reflect the promotion policy?
- Should the first version allow only grid search?
- Should training trials persist complete trades/equity snapshots or immutable summaries plus reproducibility metadata? *(2026-07-17 review recommendation: summaries + reproducibility metadata; full persistence only for selected out-of-sample runs — see Optimization trials.)*
- What embargo or feature-lag rules are required for each data source?
- Should overlapping test windows be prohibited or supported with an explicit reporting policy?
- Is a final untouched holdout required before walk-forward evidence can influence promotion?
- How should failed candidates and partially completed experiments affect group status?
- What storage-retention policy preserves auditability without unbounded growth?

## Completion Criteria

The feature may be described as full train-optimize-test walk-forward optimization only when:

- every test window has an earlier, explicitly persisted training window;
- all candidate parameters and training outcomes are auditable;
- selection uses a predetermined, versioned objective and training data only;
- selected parameters are frozen before out-of-sample execution;
- out-of-sample runs and aggregate results are reproducible from persisted metadata;
- chronological leakage checks pass for prices, features, universes, and benchmarks;
- reports clearly separate training selection from out-of-sample evidence;
- legacy rolling-window experiments remain correctly identified;
- CLI and scheduled operation work without requiring the web UI.

## Related Docs

- [Backtesting reference](backtesting.md)
- [Database diagram and terminology decisions](database-diagram-decisions.md)
- [Database schema quick reference](db-schema.md)
- [Architecture conventions](../architecture/architecture-conventions.md)
