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

## Increment 0 Work Products (Current)

1. ADR:
   - `docs/reference/adr-sleeve-virtualization-architecture.md`
2. Schema contract:
   - `docs/reference/notes-sleeve-schema-contract.md`
3. Locked simplicity decisions for Increment 1:
   - `strategy_name` as validated text
   - sleeve-only `rotation_decisions`
   - no `target_qty`/`target_notional` columns in `sleeve_orders`
   - `config_version` kept as text fields

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

### Reuse and Consolidation Focus

1. Reuse existing migration/bootstrap flow:
   - `trading/database/db_schema.py`
   - `trading/database/db_init.py`
   - `trading/database/db_migrations.py`
2. Avoid introducing a parallel schema bootstrap path for sleeve tables.
3. Keep existing account-level tables as compatibility backbone during transition, then deprecate overlap only after sleeve parity tests pass.

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

### Repo-Fit Implementation Steps (Detailed)

1. Domain transition engine:
   - Add `trading/domain/sleeve_accounting.py` as the pure state-transition module.
   - Reuse existing accounting conventions from `trading/domain/accounting.py`:
     - side normalization and validation shape
     - buy/sell cash and realized PnL semantics
     - cost-basis carry behavior on partial sells
   - Extend with sleeve-specific transition outputs:
     - deterministic slippage attribution
     - ending market value and unrealized PnL at fill mark
     - ending sleeve NAV

2. Sleeve accounting orchestration service:
   - Add `trading/services/sleeves/accounting.py`.
   - Reuse existing repositories from Increment 1 (no parallel persistence path):
     - `sleeve_orders`, `sleeve_positions`, `sleeve_ledger`, `sleeves`
   - Implement deterministic fill application flow:
     - idempotency check by `exec_id`
     - insert fill
     - write ledger cash/fee/realized entries
     - upsert or remove sleeve position
     - update sleeve cash/equity balances

3. Reconciliation service:
   - Add `trading/services/sleeves/reconciliation.py`.
   - Reuse:
     - `strategy_sleeves.current_equity` as sleeve truth
     - `equity_snapshots` latest account equity for broker-side reference
   - Emit explicit result payload:
     - sleeve equity sum
     - account equity
     - difference
     - tolerance
     - pass/fail boolean

4. Test coverage:
   - Add domain tests for buy/sell transition math and invalid fills.
   - Add service tests for fill side effects and duplicate fill idempotency.
   - Add reconciliation tests for tolerance pass/fail and missing-snapshot handling.

### Reuse and Consolidation Audit (Increment 2)

1. `trading/domain/accounting.py`: `reuse`
   - Reused accounting semantics and validation patterns.
   - Kept account-level trade replay model intact; no behavior change.

2. `trading/services/accounting/*`: `retain`
   - Existing account-scoped manual trade entry remains valid and unchanged.
   - Sleeve implementation is an additive bounded context, not a replacement yet.

3. `trading/repositories/sleeve_*` and `trading/repositories/sleeves.py`: `reuse`
   - Reused as canonical write path for sleeve accounting events.
   - No duplicate fill/position/ledger tables or alternate repository modules introduced.

4. Deprecated/removed overlap in this increment:
   - None.
   - Rationale: Increment 3 introduces sleeve-aware execution; delete/merge decisions for account-only execution pathways should be evaluated after Increment 3 parity testing.

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

### Increment 3 Slice A (Implemented)

Scope of this slice:

1. Add explicit runtime execution toggle with backward-compatible default:
   - `execution_mode=account` remains default path.
   - `execution_mode=sleeve` enables sleeve-mode orchestration path.

2. Introduce sleeve intent-generation service:
   - `trading/services/sleeves/execution.py`
   - Generates per-sleeve intents from active sleeves using:
     - sleeve assignment strategy when present
     - account active strategy fallback otherwise
   - Reuses existing trade-selection policy from auto-trading execution service.

3. Wire runtime branch without broker-layer changes:
   - Branch in `trading/services/auto_trading/runtime.py` routes sleeve mode to sleeve intent generation.
   - Account mode broker lifecycle remains unchanged.

4. Wire CLI and batch orchestration toggle:
   - `trading/interfaces/runtime/jobs/run_auto_trades.py` adds `--execution-mode`.
   - `trading/services/auto_trading/inputs.py` validates and propagates execution mode.

Slice A explicitly defers:

1. Sleeve fill ingestion and sleeve-order linkage from broker reconciliation.
2. End-to-end sleeve submission/reconciliation parity acceptance.

### Increment 3 Slice B (Implemented)

Scope of this slice:

1. Map sleeve intents to broker submissions in runtime:
   - submit generated sleeve intents through existing `BrokerConnection.place_order`.
   - keep broker lifecycle ownership in `trading/services/auto_trading/runtime.py`.

2. Persist sleeve order records at submission time:
   - create `sleeve_orders` row on submit.
   - attach `broker_order_id` when broker responds with an identifier.
   - update sleeve order status from broker status.

3. Apply immediate sleeve accounting updates for synchronous filled paper orders:
   - call sleeve accounting service to write `sleeve_fills`, update sleeve positions/ledger/cash/equity.
   - keep account-level trade history updates via existing `record_trade` pathway.

4. Keep existing broker abstraction untouched:
   - no sleeve-aware logic added inside broker adapters.
   - sleeve execution remains in service layer above brokers.

Slice B explicitly defers:

1. Full end-to-end parity assertions across all broker status permutations in sleeve mode across all brokers.

### Increment 3 Slice C (Implemented)

Scope of this slice:

1. Add asynchronous sleeve reconciliation in broker polling flow:
   - resolve sleeve orders by `account_id + broker_order_id`.
   - apply sleeve fills during reconciliation using sleeve accounting service.
   - update sleeve-order status during broker status updates.

2. Enforce idempotent sleeve fill application during repeated polling:
   - use broker `exec_id` when available.
   - use deterministic fallback execution id when broker payload omits `exec_id`.

3. Add status-path coverage for sleeve reconciliation:
   - partial fill idempotency across repeated reconciliation passes.
   - cancelled/rejected status propagation to `sleeve_orders`.
   - no unintended account-trade or sleeve-fill writes for non-filled terminal paths.

Slice C explicitly defers:

1. Multi-broker parity validation for sleeve reconciliation semantics beyond current IB-oriented flow.
2. Cross-run replay tooling for sleeve reconciliation event streams (planned under later hardening increments).

### Reuse and Consolidation Audit (Increment 3 Slice A)

1. `trading/services/auto_trading/execution.py`: `reuse`
   - Reused existing `prepare_trade_selection` policy logic.
   - No duplicate policy module introduced for sleeve mode.

2. `trading/services/auto_trading/runtime.py`: `retain + extend`
   - Retained account-mode broker execution as default path.
   - Added explicit sleeve-mode branch behind runtime toggle.

3. `trading/repositories/sleeves.py` and `trading/repositories/sleeve_positions.py`: `reuse`
   - Reused as canonical read sources for active sleeves and sleeve states.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: account-mode and sleeve-mode coexist during staged rollout until Increment 3 end-to-end parity is completed.

### Reuse and Consolidation Audit (Increment 3 Slice B)

1. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused existing broker submission and persistence patterns from account mode.
   - Extended with sleeve-order persistence and broker-id linkage in sleeve mode branch.

2. `trading/services/sleeves/accounting.py`: `reuse`
   - Reused as canonical sleeve fill application engine for synchronous filled orders.
   - Avoided duplicate fill-to-ledger implementation in runtime layer.

3. `trading/repositories/sleeve_orders.py`: `reuse`
   - Reused insert/attach/update helpers as canonical persistence path.
   - No parallel sleeve-order repository or alternative table introduced.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: account-level and sleeve-level execution flows intentionally coexist during Increment 3 rollout.

### Reuse and Consolidation Audit (Increment 3 Slice C)

1. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused existing open-order reconciliation loop and broker polling behavior.
   - Extended the loop to route fills/status updates into sleeve persistence.

2. `trading/services/sleeves/accounting.py`: `reuse`
   - Reused as the single fill-to-ledger/position/NAV transition engine for both immediate and reconciled fills.
   - Avoided introducing a separate reconciliation-only fill application path.

3. `trading/repositories/sleeve_orders.py`: `reuse + extend`
   - Added broker-order lookup helper rather than a parallel query module.
   - Continued using existing update helpers for status and broker-order linkage.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: retained compatibility overlap while closing the asynchronous reconciliation gap for sleeve mode.

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

### Increment 4 Slice A (Implemented)

Scope of this slice:

1. Add deterministic pre-trade sleeve risk gate service:
   - `trading/services/sleeves/risk_gate.py`
   - evaluates each sleeve intent and returns structured `allow`, `rescale`, or `block` decisions.

2. Initial constraints implemented:
   - sleeve symbol notional cap as percent of sleeve equity
   - account-level symbol concentration cap
   - account-level gross exposure cap

3. Wire risk gate into sleeve runtime execution:
   - apply risk gate before broker submission in sleeve mode
   - submit only approved/rescaled intents
   - preserve account-mode runtime behavior unchanged

4. Add deterministic tests:
   - allow path
   - rescale path
   - block path
   - runtime verification that rescaled qty is actually submitted/persisted

Slice A explicitly defers:

1. Kill-switch enforcement and stale-data/anomaly signals (later Increment 4 slices).
2. Sector-concentration enforcement (later Increment 4 slices).

### Increment 4 Slice B (Implemented)

Scope of this slice:

1. Persist risk decisions and kill-switch outcomes:
   - add `trading/repositories/portfolio_risk_snapshots.py`.
   - persist per-run risk payloads to `portfolio_risk_snapshots.risk_payload_json`.
   - include block/rescale reason codes and run summary counts.

2. Add sleeve-mode kill-switch checks in runtime:
   - stale price data guard before broker submission.
   - sleeve/account reconciliation mismatch guard using latest snapshot comparison.
   - broker/API anomaly guard around `place_order` failures.

3. Wire kill-switch outcomes into persisted risk snapshots:
   - set `kill_switch_triggered`.
   - persist explicit reason list and structured decision payload.

4. Add deterministic test coverage:
   - stale-price kill switch blocks submissions.
   - reconciliation-mismatch kill switch blocks submissions.
   - broker anomaly kill switch marks sleeve order rejected and persists reason.
   - repository tests for snapshot upsert/fetch semantics.

Slice B explicitly defers:

1. Sector-concentration guard implementation.
2. Dedicated normalized risk-event tables (current persistence is snapshot payload JSON).
3. External stale-data freshness timestamps beyond runtime price-validity checks.

### Reuse and Consolidation Audit (Increment 4 Slice A)

1. `trading/services/sleeves/execution.py`: `reuse`
   - Reused sleeve intent generation as the upstream input to risk gating.

2. `trading/services/auto_trading/runtime.py`: `retain + extend`
   - Retained sleeve/account runtime split and broker flow.
   - Extended sleeve flow with pre-submit gate evaluation.

3. `trading/repositories/sleeves.py` and `trading/repositories/sleeve_positions.py`: `reuse`
   - Reused as canonical sources for sleeve equity and position exposures.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: introducing gate semantics without removing any existing paths keeps rollout risk low.

### Reuse and Consolidation Audit (Increment 4 Slice B)

1. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused sleeve-mode submission workflow.
   - Extended it with kill-switch guards and risk snapshot persistence.

2. `trading/services/sleeves/reconciliation.py`: `reuse`
   - Reused for reconciliation mismatch guard instead of duplicating equity checks.

3. `trading/repositories/portfolio_risk_snapshots.py`: `new canonical persistence`
   - Introduced as the single persistence path for runtime risk decision payloads.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: existing runtime paths are preserved while adding auditable risk persistence.

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
