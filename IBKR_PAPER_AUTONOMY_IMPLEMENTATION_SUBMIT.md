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

1. Dedicated normalized risk-event tables (current persistence is snapshot payload JSON).
2. External stale-data freshness timestamps beyond runtime price-validity checks.

### Increment 4 Slice C (Implemented)

Scope of this slice:

1. Implement sector concentration guard in sleeve risk gate:
   - add `max_sector_concentration_pct` support in `SleeveRiskGateConfig`.
   - evaluate sector exposure alongside sleeve symbol, symbol concentration, and gross exposure caps.
   - emit `sector_concentration_cap` reason code when sector cap is the binding constraint.

2. Add deterministic symbol-to-sector mapping support:
   - introduce default symbol-sector map for baseline trade universe symbols.
   - allow explicit override via risk-gate config map.

3. Align runtime risk snapshot metrics with sector logic:
   - compute and persist `max_sector_concentration_pct` from current sleeve positions.
   - keep `portfolio_risk_snapshots` as canonical risk-snapshot persistence.

4. Add deterministic test coverage:
   - sector-cap block behavior in sleeve risk gate tests.
   - runtime snapshot assertion that sector concentration metric is populated.

Slice C explicitly defers:

1. External stale-data freshness timestamps beyond runtime price-validity checks.

### Increment 4 Slice D (Implemented)

Scope of this slice:

1. Add normalized risk-decision table persistence:
   - add `sleeve_risk_decisions` table and indexes.
   - add repository module `trading/repositories/sleeve_risk_decisions.py`.
   - persist one row per risk decision with action/reason/qty/notional fields.

2. Keep snapshot payload compatibility:
   - continue writing `portfolio_risk_snapshots.risk_payload_json`.
   - add normalized row persistence in parallel for queryable analytics/audit paths.

3. Wire runtime decision persistence:
   - persist gate decisions (`allow`, `rescale`, `block`) and kill-switch decisions.
   - include execution mode and payload JSON for decision-level detail retention.

4. Add deterministic test coverage:
   - repository insert/fetch tests for normalized decision rows.
   - runtime tests asserting normalized rows for rescale and kill-switch reasons.

Slice D explicitly defers:

1. External stale-data freshness timestamps beyond runtime price-validity checks.
2. Additional decision normalization for non-sleeve runtime modes (currently sleeve-mode focused).

### Increment 4 Slice E (Implemented)

Scope of this slice:

1. Add reconciliation snapshot freshness kill-switch in sleeve runtime:
   - enforce max age threshold for latest account reconciliation snapshot.
   - trigger kill-switch and block submissions when snapshot staleness exceeds threshold.

2. Persist explicit stale-snapshot decision context:
   - add `stale_reconciliation_snapshot` reason to risk payload and normalized decision rows.
   - include snapshot timestamp and threshold seconds in decision payload.

3. Keep compatibility with existing kill-switch/risk snapshot pipeline:
   - reuse existing runtime kill-switch aggregation and snapshot persistence path.
   - avoid introducing a separate stale-data pipeline for this guard.

4. Add deterministic runtime test coverage:
   - validate stale snapshot condition blocks broker submission.
   - validate persisted risk payload includes stale snapshot reason.

Slice E explicitly defers:

1. Dynamic thresholding by account volatility regime (uses fixed threshold in this slice).
2. Freshness SLA sourced from external data-health service (runtime-local threshold only).

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

### Reuse and Consolidation Audit (Increment 4 Slice C)

1. `trading/services/sleeves/risk_gate.py`: `extend existing`
   - Extended existing gate module with sector-cap logic.
   - Avoided parallel risk-policy modules.

2. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused existing risk snapshot pipeline.
   - Extended concentration calculations to include sector concentration.

3. `portfolio_risk_snapshots` persistence path: `reuse`
   - Reused existing snapshot repository and schema fields (`max_sector_concentration_pct`).

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: incremental extension preserves rollout stability.

### Reuse and Consolidation Audit (Increment 4 Slice D)

1. `portfolio_risk_snapshots` flow: `retain`
   - Retained existing snapshot payload path for backward compatibility.

2. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused existing risk decision construction flow.
   - Extended with normalized per-decision row persistence.

3. `trading/repositories/sleeve_risk_decisions.py`: `new canonical normalized store`
   - Added as dedicated queryable persistence for risk decisions.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: dual-write (snapshot payload + normalized rows) intentionally preserves compatibility while enabling structured analytics.

### Reuse and Consolidation Audit (Increment 4 Slice E)

1. `trading/services/sleeves/reconciliation.py`: `reuse`
   - Reused existing reconciliation output (`snapshot_time`) as the single freshness signal.
   - Avoided duplicate snapshot lookups in runtime.

2. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused existing kill-switch decision aggregation.
   - Extended with staleness evaluation helper and explicit stale-snapshot reason code.

3. `portfolio_risk_snapshots` and `sleeve_risk_decisions` persistence: `reuse`
   - Reused existing persistence pathways for snapshot payload + normalized decision rows.
   - No parallel persistence format introduced.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: this slice adds a missing freshness invariant without replacing existing runtime paths.

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

### Increment 5 Slice A (Implemented)

Scope of this slice:

1. Add configurable sleeve rotation scoring domain policy:
   - add `trading/domain/sleeve_rotation.py`.
   - implement weighted champion/challenger score:
     - risk-adjusted return
     - stability
     - drawdown penalty
     - cost penalty
     - regime-fit term
   - implement explicit gate evaluation:
     - cooldown
     - minimum sample size
     - outperformance threshold (bps)
     - challenger score superiority

2. Add sleeve rotation orchestration service:
   - add `trading/services/sleeves/rotation.py`.
   - build incumbent window metrics from `daily_metrics`.
   - evaluate challengers against incumbent and produce structured decision payload.
   - persist `rotation_decisions` with score components, gate results, config version, and selected `param_set_id`.
   - apply incumbent assignment switch only for `rotate` decisions.

3. Add repository read helpers required for Increment 5 scoring/cooldown:
   - `trading/repositories/daily_metrics.py`:
     - `fetch_daily_metrics_for_sleeve_window(...)`
   - `trading/repositories/rotation_decisions.py`:
     - `fetch_latest_rotate_decision_for_sleeve(...)`

4. Add deterministic test coverage:
   - `tests/trading/domain/test_sleeve_rotation.py`
   - `tests/trading/services/sleeves/test_rotation.py`
   - repository coverage additions in `tests/trading/repositories/test_sleeve_repositories.py`

Slice A explicitly defers:

1. Challenger shadow-evaluation runtime job scheduling and materialization flow.
2. Sleeve-mode runtime wiring that auto-executes Increment 5 decisions before order intent generation.

### Reuse and Consolidation Audit (Increment 5 Slice A)

1. `trading/repositories/daily_metrics.py`: `reuse + extend`
   - Reused existing sleeve metric store as incumbent evidence source.
   - Extended with windowed fetch helper only; no duplicate metric store introduced.

2. `trading/repositories/rotation_decisions.py`: `reuse + extend`
   - Reused existing decision persistence table and insert path.
   - Extended with rotate-only latest lookup for cooldown checks.

3. `trading/repositories/sleeves.py`: `reuse`
   - Reused incumbent assignment close/insert helpers as the single assignment mutation pathway.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: Increment 5 Slice A introduces policy/orchestration without replacing existing runtime rotation pathways yet.

### Increment 5 Slice B (Implemented)

Scope of this slice:

1. Wire Increment 5 rotation decisions into sleeve runtime execution path:
   - `trading/services/auto_trading/runtime.py` now executes sleeve rotation decisions before sleeve intent generation.
   - rotation actions are applied on active sleeves with incumbent assignments so `generate_sleeve_trade_intents` consumes current incumbent strategy state.

2. Add runtime challenger metric bootstrap from persisted backtest evidence:
   - derive challenger candidates from account rotation schedule.
   - map backtest return windows into `SleeveStrategyMetrics` inputs for rotation scoring.
   - bind challenger `param_set_id` through active strategy param-set lookup when available.

3. Preserve staged compatibility:
   - sleeves without active assignments are skipped (no forced failure).
   - existing account-mode runtime branch remains unchanged.

4. Add deterministic runtime tests:
   - rotation is applied before sleeve intent generation.
   - cooldown hold path preserves incumbent assignment.
   - assertions verify persisted `rotation_decisions` outcomes.

Slice B explicitly defers:

1. Dedicated scheduler job for shadow challenger materialization (currently runtime-bootstrap from existing backtest returns).
2. Advanced challenger feature inputs (regime-fit/sentiment components) beyond current baseline bootstrap.

### Reuse and Consolidation Audit (Increment 5 Slice B)

1. `trading/services/auto_trading/runtime.py`: `reuse + extend`
   - Reused existing sleeve runtime orchestration flow.
   - Extended with pre-intent rotation decision step without adding a parallel runtime entrypoint.

2. `trading/backtesting/services/history_service.py`: `reuse`
   - Reused existing `fetch_strategy_backtest_returns` evidence source for challenger bootstrap.
   - Avoided introducing a duplicate challenger evidence persistence path.

3. `trading/services/sleeves/rotation.py`: `reuse`
   - Reused Slice A rotation orchestration and persistence as the single decision engine.
   - Avoided runtime-local duplicate scoring/decision implementation.

4. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: Slice B completes runtime wiring while keeping existing account-level rotation path stable.

### Increment 5 Slice C (Implemented)

Scope of this slice:

1. Add dedicated challenger shadow-evaluation service:
   - add `trading/services/sleeves/shadow_evaluation.py`.
   - centralize account+sleeve challenger candidate materialization from:
     - account rotation schedule
     - incumbent sleeve assignments
     - backtest return evidence windows
   - emit structured challenger metrics reusable by runtime and jobs.

2. Refactor sleeve runtime to reuse shared shadow-evaluation service:
   - remove runtime-local challenger candidate construction.
   - use shared service output as the single challenger source for Increment 5 rotation decisions.

3. Add dedicated runtime job entrypoint for challenger shadow evaluation:
   - add `trading/interfaces/runtime/jobs/daily_challenger_shadow_eval.py`.
   - add enable flag/env guard, duplicate-run sentinel, per-account artifact output, and failure artifacts.

4. Add scheduler wiring for the new job:
   - extend `trading/interfaces/runtime/jobs/manage_job_schedules.py` with:
     - optional `--daily-challenger-shadow-eval-time`
     - optional `--enable-daily-challenger-shadow-eval`
     - default task name `Trading\\DailyChallengerShadowEval`

5. Add deterministic tests:
   - `tests/trading/services/sleeves/test_shadow_evaluation.py`
   - `tests/trading/interfaces/runtime/jobs/test_daily_challenger_shadow_eval_main.py`
   - scheduler build/main test updates for new task registration/unregister behavior
   - runtime sleeve-mode tests updated for shared shadow-evaluation service seam

Slice C explicitly defers:

1. Persisting challenger-evaluation snapshots into normalized DB tables (current materialization is artifact-focused).
2. Regime-fit and sentiment-weight challenger features in shadow-job outputs (currently baseline backtest-derived metrics).

### Reuse and Consolidation Audit (Increment 5 Slice C)

1. `trading/services/sleeves/shadow_evaluation.py`: `new canonical challenger materialization`
   - Introduced as single service for challenger candidate generation.

2. `trading/services/auto_trading/runtime.py`: `reuse + simplify`
   - Reused Slice B runtime hook.
   - Removed runtime-local challenger build logic in favor of shared service output.

3. `trading/interfaces/runtime/jobs/manage_job_schedules.py`: `reuse + extend`
   - Reused existing scheduler registration framework.
   - Extended with challenger shadow-eval task options rather than adding a parallel scheduler management path.

4. Deprecated/removed overlap in this slice:
   - Runtime-local challenger candidate construction helpers removed from `runtime.py`.
   - Rationale: shared service now owns challenger materialization and avoids drift between runtime and standalone shadow-eval job.

### Increment 5 Slice D (Implemented)

Scope of this slice:

1. Add optional challenger shadow-eval step into daily orchestration:
   - extend `trading/interfaces/runtime/jobs/daily_paper_trading.py` with:
     - `--run-challenger-shadow-eval`
     - `--shadow-eval-rolling-window-days`
   - when enabled, run `daily_challenger_shadow_eval` before auto-trader submissions.

2. Keep backward-compatible default behavior:
   - daily paper trading flow is unchanged unless the new flag is explicitly set.

3. Add deterministic job tests:
   - validate shadow-eval step ordering before auto-trader.
   - validate rolling-window input guardrails.

Slice D explicitly defers:

1. Default-on enablement for challenger shadow-eval step in daily scheduler configs.
2. Promotion of shadow-eval summaries into operator notifications.

### Reuse and Consolidation Audit (Increment 5 Slice D)

1. `trading/interfaces/runtime/jobs/daily_paper_trading.py`: `reuse + extend`
   - Reused existing step runner (`stream_command`) and artifact step tracking.
   - Extended with one optional pre-trade step instead of a parallel orchestration script.

2. `trading/interfaces/runtime/jobs/job_helpers.py`: `reuse + extend`
   - Reused existing module-constant pattern for subprocess job dispatch.
   - Added challenger shadow-eval module constant for consistency.

3. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: this slice wires optional orchestration only and does not replace existing job pathways.

### Increment 5 Slice E (Implemented)

Scope of this slice:

1. Add scheduler rollout defaults for challenger shadow evaluation:
   - extend `trading/interfaces/runtime/jobs/manage_job_schedules.py` with:
     - `--auto-shadow-eval-from-daily-paper`
     - `--shadow-eval-lead-minutes`
   - derive shadow-eval time from daily paper-trading schedule when explicit shadow-eval time is omitted.
   - auto-derived shadow-eval tasks include `--enable-run` to enforce explicit job activation during rollout.

2. Add operator-facing shadow-eval coverage summary into daily paper-trading artifacts:
   - `trading/interfaces/runtime/jobs/daily_paper_trading.py` now loads latest shadow-eval artifact summary and stores:
     - evaluated accounts
     - sleeves evaluated
     - challenger candidate count
   - summary is attached to DAG step-result payloads for scoring/target-build stages.

3. Add deterministic tests:
   - scheduler auto-derivation behavior and lead-minute validation
   - daily artifact embedding of shadow-eval summary metrics

Slice E explicitly defers:

1. Webhook notification enrichment with shadow-eval summary payload fields.
2. Default task-time presets for shadow-eval in deployment scripts (supports derivation but does not force defaults).

### Reuse and Consolidation Audit (Increment 5 Slice E)

1. `trading/interfaces/runtime/jobs/manage_job_schedules.py`: `reuse + extend`
   - Reused existing schedule build pipeline.
   - Extended with deterministic time-derivation helper; no parallel scheduler entrypoint added.

2. `trading/interfaces/runtime/jobs/daily_paper_trading.py`: `reuse + extend`
   - Reused existing artifact step-tracking structure.
   - Extended with shadow-eval summary hydration from exported job artifacts.

3. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: this slice enriches scheduling/reporting without replacing core execution pathways.

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

### Increment 6 Slice A (Implemented)

Scope of this slice:

1. Refactor `daily_paper_trading` into explicit numbered DAG steps:
   - `00_ingest_market_and_account`
   - `01_mark_sleeve_nav`
   - `02_run_signals_all_strategies`
   - `03_score_incumbent_vs_challengers`
   - `04_rotation_decision`
   - `05_build_position_targets_by_sleeve`
   - `06_pretrade_risk_gate`
   - `07_submit_ibkr_orders`
   - `08_reconcile_fills_update_ledgers`
   - `09_postclose_metrics_and_attribution`
   - `10_emit_report_and_alerts`

2. Add structured per-step artifact schema:
   - `step_results` now records:
     - step id/name
     - status (`pending`, `running`, `ok`, `skipped`, `failed`)
     - `started_at`, `finished_at`, `duration_seconds`
     - step details and error payload (when failed)

3. Preserve backward compatibility while enriching diagnostics:
   - keep `completed_steps` in artifact payload.
   - add `failed_step` id for failed runs.
   - keep existing runtime command behaviors and flags.

4. Add deterministic tests:
   - DAG order preservation in artifact output.
   - failed-step capture for partial-run failures.
   - existing daily config/state behavior remains covered.

Slice A explicitly defers:

1. Weekly/monthly governance job implementation.
2. Dedicated health-check consumption of new DAG step payload fields (schema now available).

### Reuse and Consolidation Audit (Increment 6 Slice A)

1. `trading/interfaces/runtime/jobs/daily_paper_trading.py`: `reuse + restructure`
   - Reused existing command execution flow and notification wiring.
   - Restructured orchestration into explicit DAG step wrappers and artifact schema.

2. `tests/trading/interfaces/runtime/jobs/test_daily_paper_trading_main.py`: `reuse + extend`
   - Reused existing behavioral coverage.
   - Extended with DAG ordering and failed-step assertions.

3. Deprecated/removed overlap in this slice:
   - None.
   - Rationale: this slice changes orchestration shape and reporting schema without introducing duplicate job entrypoints.

### Acceptance

1. End-to-end scheduled run executes without manual intervention.
2. Artifacts are written per run with machine-readable JSON payloads.
3. Health-check job can detect stale or incomplete runs.

### Increment 6 Slice B (Implemented)

Scope of this slice:

1. Enrich step 10 (`10_emit_report_and_alerts`) with a structured per-account operator report:
   - Per-account sections: sleeve performance rows, risk violations summary, rotation decisions.
   - `SleevePerformanceRow`: NAV, return metrics, drawdown from daily metrics.
   - `RiskViolationsSummary`: violation counts, kill switch state from portfolio risk snapshots.
   - `RotationDecisionRow`: rotation events for each sleeve on the report date.
   - `AccountDailyReport` dataclass aggregates all sections; serialises to dict via `account_daily_report_as_dict`.

2. Add date-bounded repository helpers:
   - `fetch_sleeve_risk_decisions_for_account_date(conn, *, account_id, report_date)` in `trading/repositories/sleeve_risk_decisions.py`.
   - `fetch_rotation_decisions_for_sleeve_date(conn, *, sleeve_id, report_date)` in `trading/repositories/rotation_decisions.py`.
   - Both use `decision_time >= date AND decision_time < next_date` bounds to scope ISO timestamp columns.

3. New service module `trading/services/sleeves/daily_report.py`:
   - Orchestrates assembly of `AccountDailyReport` from repositories.
   - Uses `fetch_latest_portfolio_risk_snapshot` for kill switch state.
   - No raw SQL in service layer (delegates to repository helpers per architecture convention).

4. Step 10 in `daily_paper_trading.py` wired to `_build_daily_operator_report` helper:
   - Opens DB via `ensure_db()`, resolves account IDs by name, builds per-account reports.
   - Embeds `report_date`, `account_count`, `account_reports` in step 10 details in the run artifact.

5. Tests:
   - 8-test suite for `daily_report.py` service using `SQLiteBackend + tmp_path` fixture pattern.
   - `test_step_10_operator_report_embedded_in_artifact` verifies step 10 artifact structure.
   - Autouse fixture stubs `_build_daily_operator_report` in all other daily-job tests to prevent DB access side effects.

Slice B explicitly defers:

1. Enriching success/failure webhook notification payloads with the operator report content.
2. Weekly and monthly governance jobs.

### Reuse and Consolidation Audit (Increment 6 Slice B)

1. `trading/repositories/sleeve_risk_decisions.py`: `reuse + extend`
   - Reused existing module; added one date-scoped query function.

2. `trading/repositories/rotation_decisions.py`: `reuse + extend`
   - Reused existing module; added one date-scoped query function.

3. `trading/services/sleeves/daily_report.py`: `new`
   - No prior equivalent; added as new capability module in the existing sleeves service package.

4. `trading/interfaces/runtime/jobs/daily_paper_trading.py`: `reuse + extend`
   - Reused DAG structure from Slice A; wired step 10 with real operator report assembly.

5. `tests/trading/services/sleeves/test_daily_report.py`: `new`
   - Fresh test suite for new service module.

6. `tests/trading/interfaces/runtime/jobs/test_daily_paper_trading_main.py`: `reuse + extend`
   - Added step 10 test and autouse DB-isolation fixture without altering existing tests.

7. Deprecated/removed overlap in this slice:
   - None.

### Acceptance (Increment 6 Slice B)

1. Step 10 artifact section contains `report_date`, `account_count`, and `account_reports` on each run.
2. Per-account report includes sleeve performance, risk violations (with kill switch flag), and rotation decisions.
3. All 22 affected tests pass; no DB-access side effects in unrelated daily-job tests.

### Increment 6 Slice C (Implemented)

Scope of this slice:

1. Six standalone weekly and monthly governance job entrypoints:

   **Weekly jobs (dedup guard: ISO week tag):**
   - `weekly_governance_w1_leaderboard`: 30-day sleeve performance ranking per account; sleeves ranked by `avg_risk_adjusted_score`.
   - `weekly_governance_w2_promotion_review`: promotion readiness and sleeve status per account using `fetch_current_promotion_assessment`; reports `ready_for_live` and `blockers`.
   - `weekly_governance_w3_allocation_review`: compares actual sleeve NAV allocation vs original `start_equity` ratios; flags sleeves where `|drift_pct| >= threshold` (default 5%).

   **Monthly jobs (dedup guard: calendar month tag `YYYY_MM`):**
   - `monthly_governance_m1_risk_rebaseline`: latest portfolio risk snapshot per account for operator monthly review; includes kill switch state, exposure, drawdown.
   - `monthly_governance_m2_parameter_governance`: active strategy param set inventory per sleeve; operator reviews parameter health without automated enforcement.
   - `monthly_governance_m3_performance_audit`: 90-day compound return, max drawdown, average hit rate, and total trades per sleeve; configurable `--audit-window-days`.

2. Six new completion sentinels in `common/runtime_job_status.py`; re-exported from `trading/interfaces/runtime/job_status.py`.

3. All 6 jobs are read-only against the DB — no writes, no mutations.

4. Each job writes a timestamped JSON artifact to `local/artifacts/` and supports `--force-run` to bypass the dedup guard.

5. 39 deterministic tests across 6 files: dedup guard skip, sentinel detection, artifact key structure, and job-specific computations (ranking, drift math, cumulative return, null stats).

Slice C explicitly defers:

1. Scheduling registration in `manage_job_schedules.py` (operator can schedule manually with cron/Task Scheduler).
2. Automated promotion/retirement actions triggered by W2 output (read-only reports only).
3. Automated risk budget updates triggered by M1/M2 output.

### Reuse and Consolidation Audit (Increment 6 Slice C)

1. `common/runtime_job_status.py`: `reuse + extend`
   - Added 6 new sentinel constants; no existing sentinels changed.

2. `trading/interfaces/runtime/job_status.py`: `reuse + extend`
   - Re-exported 6 new sentinels; existing exports unchanged.

3. `trading/interfaces/runtime/jobs/weekly_governance_w[1-3]*.py`: `new`
   - Three new standalone weekly job entrypoints following `weekly_db_backup.py` dedup pattern.

4. `trading/interfaces/runtime/jobs/monthly_governance_m[1-3]*.py`: `new`
   - Three new standalone monthly job entrypoints following the same pattern with a `month_tag` variant.

5. `tests/trading/interfaces/runtime/jobs/test_weekly_governance_*.py` + `test_monthly_governance_*.py`: `new`
   - Six new test files; each follows the `run_runtime_job_main` helper pattern from existing daily job tests.

6. No repositories were modified — all queries use existing read functions.

7. Deprecated/removed overlap in this slice:
   - None.

### Acceptance (Increment 6 Slice C)

1. All 6 governance jobs run to completion as standalone `python -m` invocations.
2. Dedup guards prevent duplicate weekly/monthly runs without `--force-run`.
3. Artifacts land in `local/artifacts/` with correct JSON structure for each job type.
4. All 39 new tests pass; no mutations to existing tests or repository code.

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
