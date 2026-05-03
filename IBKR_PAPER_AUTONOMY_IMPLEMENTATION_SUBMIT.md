# IBKR Paper Autonomy Implementation Submit

## Purpose

Translate `IBKR_PAPER_AUTONOMY_PLAN.md` into repo-specific implementation steps based on the current codebase.

## Document Relationship

1. `IBKR_PAPER_AUTONOMY_PLAN.md` is the strategic source of truth.
2. This submit document is the implementation source of truth.

Synchronization rule:

1. If strategy, scope, or acceptance outcomes change, update the plan first.
2. If sequencing, tasks, or repo-level execution details change, update this file.
3. Every implementation PR must reference both documents and note whether either was updated.

## Current Repo Baseline (What Already Exists)

1. Runtime scheduler entrypoints and registration are implemented.
   - `trading/interfaces/runtime/jobs/manage_job_schedules.py`
   - `trading/interfaces/runtime/jobs/daily_paper_trading.py`
   - `trading/interfaces/runtime/jobs/daily_backtest_refresh.py`

2. Auto-trading execution and broker submission loop already exist at account scope.
   - `trading/services/auto_trading/runtime.py`
   - `trading/services/auto_trading/execution.py`
   - `trading/interfaces/runtime/jobs/run_auto_trades.py`

3. Broker abstraction and IBKR Web adapter integration exist.
   - `trading/brokers/base.py`
   - `trading/brokers/factory.py`
   - `trading/brokers/ib_web_adapter.py`
   - `trading/brokers/ib_web_client.py`

4. Account-level persistence for orders, fills, trades, snapshots, and rotation episodes exists.
   - `trading/database/db_schema.py`
   - `trading/repositories/broker_orders.py`
   - `trading/repositories/trades.py`
   - `trading/repositories/rotation.py`
   - `trading/repositories/snapshots.py`

5. Rotation, evaluation, and promotion governance are partially present.
   - `trading/services/auto_trading/rotation.py`
   - `trading/services/evaluation/evidence.py`
   - `trading/services/promotion/*`

## Gap Summary (What Is Missing vs Plan)

1. No sleeve domain model or sleeve tables exist yet.
2. No sleeve-level ledger, positions, NAV, or order ownership.
3. No cross-sleeve portfolio risk gate or deterministic rescaling engine.
4. Rotation today is account-level schedule/backtest/regime selection; no explicit challenger sleeve lifecycle with thresholded decision records.
5. Daily runtime is single account-trade loop + snapshot/report calls; it is not the explicit DAG in the plan.
6. Sentiment exists as rotation overlay/regime input but not as sleeve-level challenger scoring component with controlled weight and audit binding.
7. No explicit config version binding from order/decision/metric records to parameter set versions.

## Architecture Constraints to Preserve

1. Keep canonical dependency direction:
   - `interfaces -> services -> repositories/domain -> database`
2. Keep policy math in `trading/domain/*`.
3. Keep SQL in `trading/repositories/*`.
4. Keep runtime orchestration in `trading/interfaces/runtime/jobs/*`.
5. Keep broker SDK and API details in `trading/brokers/*`.

## Reuse and Consolidation Objective

During implementation, prioritize reuse of existing modules and remove or merge obsolete overlap introduced by the new sleeve model.

### Rules

1. Reuse before rewrite:
   - If existing code can satisfy a requirement with targeted extension, extend it.
   - Do not introduce parallel implementations for the same behavior.

2. Consolidate duplicate pathways:
   - When sleeve-mode replaces an older account-only pathway for the same responsibility, either:
     - remove the old path, or
     - keep it behind a clear compatibility boundary with deprecation notes.

3. Require a per-increment overlap audit:
   - For each increment, list touched modules and any similar existing logic.
   - Decide explicitly: `reuse`, `merge`, `deprecate`, or `retain`.

4. Keep deletion safe:
   - Remove only after tests and runtime parity checks pass for the replacement path.
   - If immediate deletion is risky, mark with a dated deprecation note and follow-up issue.

### Consolidation Acceptance Gate (applies to every increment)

1. No net-new duplicate runtime entrypoint for equivalent behavior without written justification.
2. No duplicate persistence writes for the same event across old/new paths.
3. Updated module ownership notes when responsibility moves.
4. Changelog section in PR notes:
   - reused components
   - merged components
   - deprecated/removed components

## Target Delivery Strategy

Implement in seven increments so each merge is deployable and testable.

## Increment 0: ADR + Schema Contract Freeze

### Deliverables

1. Add an architecture decision record describing sleeve semantics and constraints:
   - one broker account, many sleeves
   - broker truth remains account-level
   - sleeve attribution is internal book-keeping

2. Define final table contracts and indexes for:
   - `strategy_sleeves`
   - `sleeve_strategy_assignments`
   - `strategy_param_sets`
   - `sleeve_orders`
   - `sleeve_fills`
   - `sleeve_positions`
   - `sleeve_ledger`
   - `portfolio_risk_snapshots`
   - `rotation_decisions`
   - `daily_metrics`

3. Define immutable IDs and referential keys:
   - strategy identifiers
   - param set identifiers
   - broker order mapping strategy

### Acceptance

1. ADR approved.
2. Table schema and index plan approved.
3. Migration rollback strategy documented.

## Increment 1: Database and Repository Foundation

### Deliverables

1. Add schema SQL for new tables in `trading/database/db_schema.py`.
2. Add migrations and migration hooks in:
   - `trading/database/db_migrations.py`
   - `trading/database/db_init.py`
3. Add repository modules:
   - `trading/repositories/sleeves.py`
   - `trading/repositories/sleeve_orders.py`
   - `trading/repositories/sleeve_positions.py`
   - `trading/repositories/sleeve_ledger.py`
   - `trading/repositories/rotation_decisions.py`
   - `trading/repositories/daily_metrics.py`

### Acceptance

1. Fresh DB init includes all new tables and indexes.
2. Existing DB migrates forward idempotently.
3. Repository tests cover CRUD and idempotency behavior.

## Increment 2: Sleeve Accounting Engine

### Deliverables

1. Add domain accounting model for sleeve-level state:
   - cash
   - realized/unrealized PnL
   - open position cost basis
   - NAV

2. Add service orchestrators:
   - `trading/services/sleeves/accounting.py`
   - `trading/services/sleeves/reconciliation.py`

3. Implement deterministic fill-to-ledger rules:
   - buy/sell fill handling
   - fee and slippage attribution
   - position average cost updates

4. Add reconciliation check:
   - sum(sleeve equity) vs account equity tolerance

### Acceptance

1. Unit tests for accounting transitions pass.
2. Reconciliation report emitted with explicit tolerance result.
3. No impact on current account-level trade history behavior.

## Increment 3: Sleeve-Aware Execution Path

### Deliverables

1. Introduce sleeve-aware target generation in service layer:
   - generate per-sleeve intents
   - map intents to broker orders

2. Extend runtime order persistence:
   - bind each order/fill to `sleeve_id`, `strategy_id`, `param_set_id`

3. Preserve current broker abstraction:
   - no direct sleeve logic in broker adapter
   - sleeve logic remains above broker layer

4. Add staged rollout toggle:
   - account-level mode (current)
   - sleeve mode (new)

### Acceptance

1. Sleeve mode can run paper orders end-to-end.
2. Account mode remains backward compatible.
3. Fill reconciliation updates both account and sleeve views consistently.

## Increment 4: Risk Gate and Rescaling

### Deliverables

1. Implement pre-trade risk gate service:
   - sleeve notional cap
   - symbol concentration
   - sector concentration
   - max daily loss
   - gross exposure

2. Implement deterministic rescaling policy:
   - initial mode: proportional down-scaling by risk budget
   - alternate modes behind config for future expansion

3. Add kill-switch checks:
   - stale data
   - reconciliation mismatch
   - broker/API anomaly

### Acceptance

1. Risk gate returns structured decision payloads.
2. Every blocked/rescaled action is persisted with reason code.
3. Integration tests validate deterministic behavior for identical inputs.

## Increment 5: Challenger Evaluation and Rotation Decisions

### Deliverables

1. Add configurable scoring pipeline service:
   - rolling windows
   - sample-size gates
   - outperformance threshold
   - drawdown and cost penalties
   - optional regime-fit term

2. Add challenger shadow-evaluation jobs.
3. Implement rotation decision recording and cooldown enforcement.
4. Bind decisions to config version + param set IDs.

### Acceptance

1. Rotation decisions are explainable and replayable from persisted data.
2. Cooldown and gate violations are explicitly logged.
3. Regression tests cover no-rotate and rotate cases.

## Increment 6: Runtime DAG and Reporting

### Deliverables

1. Refactor `daily_paper_trading` into explicit step graph aligned with plan:
   - ingest
   - sleeve mark
   - signal run
   - scoring
   - decision
   - risk gate
   - submit
   - reconcile
   - metrics
   - report/alerts

2. Add weekly/monthly jobs for governance reviews.
3. Add operator artifacts:
   - daily run report
   - sleeve performance table
   - risk violations
   - rotation decision summary

### Acceptance

1. End-to-end scheduled run executes without manual intervention.
2. Artifacts are written per run with machine-readable JSON payloads.
3. Health-check job can detect stale or incomplete runs.

## Increment 7: Hardening and Burn-In

### Deliverables

1. Replay/backfill tooling for missed runs.
2. Runbook updates for operators.
3. Burn-in protocol:
   - shadow period
   - stability thresholds
   - promotion gate to autonomous mode

### Acceptance

1. Consecutive burn-in run target achieved with no critical failures.
2. Reconciliation and risk checks remain within thresholds.
3. Go-live checklist signed off.

## Testing Plan

1. Unit tests for:
   - sleeve accounting
   - risk gate
   - scoring and rotation policy

2. Repository tests for all new sleeve tables.
3. Job integration tests for daily/weekly/monthly DAG paths.
4. Replay tests using recorded artifacts to verify deterministic outcomes.
5. Backward compatibility tests for current account-level runtime mode.

## Proposed Delivery Timeline

1. Increment 0-1: 1.5 to 2.5 weeks
2. Increment 2-3: 2.0 to 3.0 weeks
3. Increment 4-5: 2.0 to 3.5 weeks
4. Increment 6-7: 2.0 to 3.0 weeks

Estimated total:

1. One engineer: 8 to 12 weeks
2. Two engineers with disjoint workstreams: 5 to 8 weeks

## Recommended Immediate Next Steps

1. Approve this submit document and lock Increment 0 outputs.
2. Implement Increment 1 first with full repository test coverage.
3. Keep current runtime path as default until Increment 3 passes integration tests.
4. Enable sleeve mode only behind explicit config and operator opt-in.
5. Include a reuse/consolidation audit summary in every implementation PR for this program.
