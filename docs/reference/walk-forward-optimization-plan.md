# Walk-Forward Optimization Plan

Type: notes
Status: Active
Created: 2026-07-17
Last Reviewed: 2026-07-21
Purpose: Define the accepted leakage-safe methodology for evolving rolling-window tests into full train-optimize-test walk-forward optimization.
Related: [Research Persistence and Walk-Forward Completion Plan](research-persistence-review.md), [Backtesting](backtesting.md), [Database Transactions](database-transactions.md), [Database Schema](db-schema.md)

## Purpose

This document owns the financial methodology, leakage controls, optimization rules, and evaluation
honesty requirements for full walk-forward optimization. The
[Research Persistence and Walk-Forward Completion Plan](research-persistence-review.md) owns schema
sequencing, delivery phases, and progress.

This is a plan until its completion criteria are implemented. It must not be read as a claim that
the current workflow already performs optimization.

## Current Capability

The current workflow executes a fixed strategy across chronologically shifted test windows. It
stores each simulation as a normal backtest and groups the window results.

This is **rolling-window robustness testing**. It is useful evidence, but it is not full
walk-forward optimization because it has no earlier training interval, candidate trials,
predeclared selection objective, frozen winner, or untouched final holdout.

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
immutable parameter injection, trial summaries, input artifacts, and evidence-aware reporting.

## Window Methodology

### Training policies

Support both policies as explicit experiment configuration:

- **Rolling:** use the fixed-length interval immediately preceding each test window.
- **Expanding:** use a fixed inception date and extend training through the date immediately before
  each test window.

Production defaults are 12 training months, 1-month test windows, 1-month steps, and a final
untouched 6-month holdout. These values remain configurable and must be persisted.

Each window persists `train_start`, `train_end`, `test_start`, and `test_end`. Training must end
before testing starts. The final holdout is excluded from every training and OOS interval.

### Warm-up and source availability

Indicator warm-up observations may precede a scoring interval, but they are used only to initialize
calculations. They do not count toward objective metrics or eligibility sample sizes. Persist the
warm-up policy with the experiment and run manifests.

Price-only daily strategies may use zero embargo because signals use prior-day values and execute on
the next bar. External features must declare their point-in-time availability or publication lag.
Apply that lag during construction and persist it with the source provenance. An explicit positive
embargo remains available when a source requires additional separation.

An embargo is not a substitute for point-in-time data. Revised external data is eligible only when
the stored artifact represents what would have been available at the simulated decision time.

### OOS overlap

Require `step_months >= test_months`. Reject overlapping OOS windows rather than silently
double-counting dates in stitched results. Steps longer than test windows may create labeled gaps;
reports must not imply continuous exposure across those gaps.

## Candidate Search

Candidate parameters come from an explicit, bounded search-space snapshot compatible with the
strategy primitive's existing validation schema. Optimization must never mutate
`strategies.params_json`; the simulator receives an immutable validated override.

Use a pluggable optimizer interface with two initial implementations:

- exhaustive deterministic grid search;
- seeded random search.

Every experiment persists optimizer name/version, canonical search-space snapshot, candidate
budget, and seed where applicable. Random search requires an explicit seed. Candidate ordering and
canonical parameter serialization must be deterministic. Reject a grid whose Cartesian product
exceeds the explicit candidate budget rather than truncating it invisibly.

Bayesian or adaptive search is outside the initial completion boundary. A future optimizer must
persist all model state, search history, stopping rules, and seeds needed to explain its choices.

## Objective and Eligibility

The initial objective is `calmar_v1`. It is selected before execution and applied identically to
every candidate and window.

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

The one-percentage-point denominator floor makes the zero-drawdown case finite and persistable.
Rank higher scores first. Deterministic ties resolve by:

1. higher annualized return;
2. lower absolute drawdown;
3. higher execution count;
4. canonical candidate order.

Persist the objective name/version, value, component metrics, eligibility, rejection reasons, and
tie-break fields for every candidate. If no candidate is eligible, fail the experiment; never select
the least-bad ineligible candidate.

Test and holdout results are evaluation outputs only. They must never influence candidate ranking or
cause an earlier winner to be replaced.

## Persistence and Failure Semantics

Persist trial summaries rather than full training result trees. Each trial records:

- canonical parameters and hash;
- candidate and optimizer sequence;
- objective components and value;
- eligibility and structured rejection reasons;
- execution status, warnings, duration, and reproducibility provenance;
- whether it was selected.

Full executions and equity snapshots are reserved for selected OOS and final-holdout runs.
Experiment/window tables own membership; shared `backtest_runs` rows own complete simulator results.
The final table ownership and migration are specified in the
[completion plan](research-persistence-review.md#final-schema-direction).

The workflow is fail-fast:

- roll back the active trial or complete backtest unit;
- persist structured failure diagnostics on the trial/window and experiment boundary;
- stop the experiment immediately;
- retry by creating a new experiment rather than resuming or mutating the failed experiment.

Failed experiment metadata is audit evidence. Partial backtest executions or equity trees are not.

## OOS and Holdout Evaluation

After candidate selection, freeze the selected parameters and manifest before the OOS interval
begins. Execute each OOS period exactly once for that experiment.

Report two OOS views:

- a window distribution containing return, drawdown, execution count, dispersion, and diagnostics;
- a chain-linked chronological series assembled from non-overlapping OOS periods.

Do not sum or directly concatenate independently reset account equity values. Chain-link returns and
label any gaps introduced by a step longer than the test interval.

After all OOS windows complete, run the selected process over the untouched 6-month holdout. The
holdout is required before this new optimization evidence can satisfy research promotion. Promotion
uses completed, reproducible OOS and holdout evidence and the configured promotion gates; it does
not use training performance as realized evidence.

Legacy rolling-window experiments remain reportable but do not satisfy the full optimization
requirement.

## Reproducibility and Leakage Controls

Every candidate, OOS run, and holdout must resolve to immutable effective inputs:

- validated strategy parameters;
- initial capital, benchmark, fees, slippage, execution, and warm-up configuration;
- exact universe membership;
- market and feature data artifacts with provider and as-of metadata;
- engine/objective/optimizer versions and source/build provenance.

Required controls:

| Risk | Control |
|---|---|
| Look-ahead | Enforce boundaries in pure domain logic and prove ranking sees training results only. |
| External-data revision | Store point-in-time artifacts and availability lags, not only current provider output. |
| Parameter overfitting | Bound and disclose the search space, candidate count, OOS sequence, and untouched holdout. |
| Multiple testing | Persist every attempted candidate summary rather than only the winner. |
| Regime specialization | Compare window stability and chain-linked OOS behavior, not only an aggregate return. |
| Inconsistent assumptions | Freeze one manifest and input artifact set for comparable candidates. |
| Misleading reporting | Label training, OOS, and holdout metrics separately and never blend them. |

## Architecture Alignment

Follow the existing dependency direction:

- `backtesting/domain/`: pure boundaries, search generation, objective calculation, eligibility,
  ranking, tie-breaks, chain-linking, and leakage validation;
- `backtesting/models/`: passive configuration, manifest, artifact, experiment, trial, selection,
  and report contracts;
- `backtesting/repositories/`: SQL persistence and purpose-aware evidence queries;
- `backtesting/services/`: data resolution, orchestration, atomic execution, failure recording, and
  reporting;
- `interfaces/cli/`: operator inputs and output over the shared services.

Infrastructure owns concrete market-data and artifact-storage adapters. Domain and service code must
not import those implementations directly.

Web parity, a scheduled runtime job, resumability, Bayesian optimization, and automatic artifact
pruning are separate work and do not block the accepted CLI/service completion boundary.

## Validation Strategy

Automated coverage must include:

- exact rolling and expanding boundaries;
- warm-up exclusion and source-specific availability lags;
- final-holdout isolation and OOS overlap rejection;
- deterministic grid and seeded-random candidate generation;
- parameter validation without catalog mutation;
- objective eligibility, denominator floor, rejection, and tie-breaking;
- proof that ranking receives training data only;
- consistent assumptions and artifacts across candidates;
- atomic OOS and holdout persistence;
- fail-fast experiment state without partial backtest trees;
- chain-linked OOS aggregation without duplicate dates;
- reports that keep training, OOS, and holdout evidence distinct;
- promotion exclusion for legacy, failed, incomplete, or non-reproducible evidence.

Include a deterministic changing-regime fixture whose expected winners and OOS results are fixed by
construction rather than incidental live market data.

## Completion Criteria

The capability may be called full train-optimize-test walk-forward optimization only when:

- every OOS window has an earlier persisted training interval;
- all attempted candidates and outcomes are auditable;
- selection uses only a predetermined versioned objective and training evidence;
- selected parameters are frozen before OOS execution;
- actual input artifacts and manifests support offline reproduction;
- chronological leakage checks pass for prices, features, universes, and benchmarks;
- OOS windows are non-overlapping and aggregated honestly;
- an untouched final holdout is executed after OOS completion;
- reports and promotion keep training, OOS, and holdout evidence distinct;
- legacy rolling tests remain correctly identified;
- shared services and CLI operation work without requiring the web UI.

Implementation phases and progress are tracked in the
[Research Persistence and Walk-Forward Completion Plan](research-persistence-review.md#implementation-phases).

## Related Docs

- [Research persistence and walk-forward completion plan](research-persistence-review.md)
- [Backtesting reference](backtesting.md)
- [Database transactions](database-transactions.md)
- [Database schema](db-schema.md)
- [Database diagram and terminology decisions](database-diagram-decisions.md)
- [Architecture conventions](../architecture/architecture-conventions.md)
