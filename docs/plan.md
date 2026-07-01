# Execution Plan & Task Tracker

Type: plan
Status: Active
Created: 2026-06-29
Last Reviewed: 2026-07-01
Purpose: The single source for tasks, order, status, and timelines — the itemized backlog and progress tracker. What needs to be *defined* (open decisions) lives in [decisions.md](decisions.md); the entry-point north star is [overview.md](overview.md).
Related: [Overview](overview.md), [Decisions](decisions.md), [Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md), [DB Schema Rewrite Spec](db-schema-rewrite-spec.md), [Developer Notes](developer-notes.md)

> Single source for **priority order / status / timelines**. Open decisions ("what needs defining")
> are in [decisions.md](decisions.md); the entry-point overview is [overview.md](overview.md).

## Priority board

One ordered list (P1 = do first). Estimates are rough t-shirt sizes: **S** ≈ ≤1 day ·
**M** ≈ a few days · **L** ≈ ~1–2 weeks.

| P | Initiative | Commitment | Status | Est | Gate |
|---|---|---|---|---|---|
| 1 | Close the execution loop (keystone) | Committed | ☐ next up | L | [D1](decisions.md#d1) |
| 2 | Finish unified evaluation (1c) | Committed | ◑ 1a✅ · 1b✅ · 1c☐ | S | — |
| 3 | DB schema rewrite (greenfield, option B) | Committed | ✎ spec ready | L | [D4](decisions.md#d4), [D5](decisions.md#d5) |
| 4 | Converge accounts & sleeves (once, on clean schema) | Committed | ☐ | L | — |
| 5 | Decisioning legibility & naming pass | Committed | ☐ | M | [D13](decisions.md#d13) |
| 6 | Plug-and-play strategy & provider catalog | Committed | ☐ | L | [D5](decisions.md#d5) |
| 7 | Unified parameter source | Committed | ☐ | L | [D4](decisions.md#d4) |
| 8 | Email notifications (independent) | Committed | ☐ | M | [D8](decisions.md#d8) |
| 9 | Portfolio risk rollup | Committed | ☐ | M | [D10](decisions.md#d10) |
| 10 | Adaptive learning | Exploratory | ☐ | L | [D9](decisions.md#d9) |
| 11 | Strategy parameter optimization | Exploratory | ☐ | L | [D11](decisions.md#d11) |

**Commitment:** Committed = will build, in order · Conditional = committed but gated on an open
decision · Exploratory = only if evidence justifies. **Status:** ✅ done · ◑ in progress ·
✎ spec ready · ☐ not started.

## Product Goal

Keep the system simple, robust, and evidence-driven while supporting:

- multiple strategy families
- continuous comparison and rotation
- controlled use of external signals
- explicit paper-to-live promotion gates

Guiding constraints: keep live execution explicitly human-gated, keep overlays
conservative and interpretable, and unify comparison, rotation, and promotion around
one canonical evaluation model.

## Already delivered (out of scope here)

These baseline capabilities are in place and are not tracked as future work:

- multi-strategy backtesting and walk-forward workflows
- paper trading with snapshots, trades, and account-level benchmark overlays
- persisted promotion review workflow with append-only audit history
- scheduled daily backtest refresh job with idempotency, retry, and artifacts
- guarded live-broker path with explicit live activation controls
- canonical evaluation artifact (`src/trading/services/evaluation/evidence.py`) backing
  promotion and reporting summaries

## Outstanding partials

- **Unified evaluation** — promotion (`src/trading/services/promotion/assessment.py`),
  reporting (`src/trading/services/reporting/presentation.py`), and compare account payloads
  (`apps/paper_trading_web/backend/routes/accounts.py`) read the canonical evaluation artifact.
  Sleeve rotation (`src/trading/services/sleeves/rotation.py`) still scores on return-based
  metrics instead of canonical score/confidence. See
  [P2 — Unify evaluation](#unify-evaluation-across-decision-surfaces).
- **`learning_enabled`** — active as heuristic exploration (account-profile flag in
  `src/infrastructure/config/account_profiles/*.json` plus a DB column), but with no persisted,
  versioned learned state. See [P10 — Adaptive learning](#true-adaptive-learning).

## Sequencing

Rationale for the priority board order (the board above is the canonical ordered list):

1. **P1 — Close the execution loop (keystone).** Schema-agnostic and the highest-value gap: the live
   path does not run strategy signals today. Do it first, on the current schema.
2. **P2 — Finish unified evaluation (1c).** 1a/1b are done; add the cross-surface regression tests.
3. **P3 — DB schema rewrite (greenfield, option B).** Decided ([D2](decisions.md#d2)/[D3](decisions.md#d3)):
   rewrite-first. No data to lose and pre-live is the cheapest time to change schema.
4. **P4 — Converge accounts & sleeves, built once on the clean schema** (submission/rotation/
   accounting) rather than migrating two live paths — with **P5** (naming pass) done alongside.
5. **P6–P7** land on the new schema (plug-and-play catalog, parameter source). **P8** (email) is
   independent and can slot in anytime; **P9** (risk rollup) follows.
6. **P10–P11** are Exploratory — pursued only if evidence justifies.

## Initiatives (detail)

Reference entries. Ordered priority, commitment, and status live in the priority board above.

#### DB schema rewrite (greenfield, option B)

Priority: P3 · Committed

Decided B ([D2](decisions.md#d2)/[D3](decisions.md#d3)). Full detail in the
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md) and [DB Schema Target](db-schema-target.md);
open schema-detail decisions: [D4](decisions.md#d4), [D5](decisions.md#d5), [D6](decisions.md#d6).

#### Unify evaluation across decision surfaces

Priority: P2 · Committed

- Scope: one canonical evaluation output drives compare, rotation selection, and promotion decisions.
- Surface: `src/trading/`, `apps/paper_trading_web` (backend + frontend compare/admin views).
- Why it matters: today there are three scoring notions in the codebase, and rotation's
  champion/challenger comparison is internally inconsistent — the incumbent is scored from live
  `daily_metrics` (`src/trading/services/sleeves/rotation.py`) while challengers are scored from
  backtest returns (`src/trading/services/sleeves/shadow_evaluation.py`), and the canonical
  `StrategyEvaluationArtifact` (`src/trading/services/evaluation/evidence.py`) is a third,
  confidence-weighted return blend. Unifying is both a consolidation and a correctness fix.
- Delivered so far:
  - [x] **Evaluation visibility** — promotion overview returns canonical evaluation evidence and
    confidence detail; account compare API/UI exposes canonical blended score, confidence, and
    data gaps (`apps/paper_trading_web/backend/services/evaluation.py`).
- Decisions to resolve before 1a:
  - **Score semantics** — rotation uses a multi-component gated score
    (`risk_adjusted_return + stability − drawdown − cost + regime_fit`); the artifact exposes a
    confidence-weighted return `blended_score`. Decide whether rotation consumes `blended_score`
    directly, the artifact is enriched with rotation's components, or a new shared decision score is
    defined that both derive.
  - **Granularity** — the artifact is per (account, strategy); rotation needs (strategy, param_set).
    Decide whether the adapter keys on param_set or keeps it outside the score.
  - **Evidence source per role** — pick one evidence source per role so the incumbent and
    challengers stop being scored from different data.
- Sub-features (independent, shippable separately):
  - [ ] **1a. Shared decision-score contract** — define the contract shape in
    `src/trading/models/evaluation/` (or the sleeve decision-model boundary, no UI-only fields in
    trading services) and add a `trading.services.evaluation`/`trading.domain` adapter that derives
    decision-ready score, confidence, and data-gap status from `StrategyEvaluationArtifact`. Wire
    compare and promotion payload builders onto the adapter instead of reading confidence fields
    directly. No behavior change.
  - [ ] **1b. Rotation migration** — repoint both the incumbent and the challengers in
    `src/trading/services/sleeves/rotation.py` and `shadow_evaluation.py` onto the 1a contract,
    keeping cooldown, trade-count, and outperformance gates explicit and re-deriving the
    outperformance-bps gate against the new score. Collapses the parallel incumbent/challenger
    metric builders where possible.
  - [ ] **1c. Contract regression tests** — prove compare, promotion, and rotation read the same
    score/confidence contract and handle complete evidence, missing backtest evidence, missing
    paper/live evidence, and null blended score identically.
- Remaining work is 1c only. Estimate: **S** (test-only).
- Code areas that will change (1c):
  - `tests/src/trading/domain/test_evaluation_decision_score.py` (extend) and/or a new
    `tests/src/trading/services/test_decision_contract_consistency.py` proving compare
    (`apps/paper_trading_web/backend/services/evaluation.py`), promotion
    (`src/trading/domain/promotion_policy.py` confidence/data-gap reads), and rotation
    (`src/trading/services/sleeves/shadow_evaluation.py`) all derive from `derive_decision_score` and
    handle missing evidence identically. Reuse `tests/support/evaluation.py` fixtures.
- Done when:
  - [x] compare surfaces expose canonical score/confidence fields
  - [ ] a single decision-score contract backs compare, promotion, and rotation (1a)
  - [ ] rotation scoring reads the contract rather than separate return-only paths, with incumbent
    and challengers scored from the same source (1b)
  - [ ] regression tests cover score usage across all three surfaces (1c)

#### Converge accounts and sleeves on shared services

Priority: P4 · Committed

- Scope: remove the parallel account-mode vs sleeve-mode orchestration by routing both through
  shared, single-responsibility services. Consolidation is incremental and opportunistic — build
  each shared service as roadmap work touches that code and migrate the account and sleeve paths one
  seam at a time, so pre-submit safety only ever strengthens. No big-bang rewrite of the live path.
- Full plan and progress tracker: [Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md).
- Surface: `src/trading/services/auto_trading/`, `src/trading/services/sleeves/`,
  `src/trading/services/accounting/`.
- Architecture direction: the environment axis (test/UI paper sim, IBKR paper, future live) is
  already converged behind the `BrokerConnection` port + `get_broker_for_account` factory and the
  `live_trading_enabled` guard — a new environment is one adapter plus one factory branch. Keep new
  code honoring the injected `broker_factory` (never construct brokers inline). The duplication to
  remove is the accounts-vs-sleeves axis, not the environment axis.
- Current duplication (evidence):
  - order submission + broker-order persistence + on-fill ledger update is implemented twice: the
    account path via `_broker_aware_record_trade` and the sleeve path inline in
    `_run_sleeve_mode_for_account`, both in `src/trading/services/auto_trading/runtime.py`.
  - pre-submit safety is asymmetric: sleeve mode has kill switches (stale price, reconciliation
    mismatch/staleness) that account mode lacks.
  - ledger updates diverge: account mode calls `record_trade`; sleeve mode calls `apply_sleeve_fill`
    then `record_trade`.
  - rotation is split across two paradigms and several modules (`auto_trading/rotation.py`,
    `runtime_rotation.py`, `rotation_bridge.py`, `sleeves/rotation.py`, `shadow_evaluation.py`) — the
    same root cause as P2.
- Sub-features (independent; each migrates account + sleeve one seam at a time):
  - [ ] **2a. Shared order-submission service** — extract "submit intent → persist broker order →
    on-fill ledger update" into one service (e.g. `src/trading/services/execution/`) that both modes
    call, differing only by an injected on-fill handler (account ledger vs sleeve ledger). Fold the
    pre-submit safety gates in so account mode inherits the sleeve kill switches. Highest-value slice
    and directly reduces live-path risk.
  - [ ] **2b. Unified rotation/selection** — collapse account episode rotation and sleeve
    champion/challenger onto the P2 decision-score contract, and reduce the rotation module
    sprawl. Depends on 1a.
  - [ ] **2c. Unified accounting/ledger path** — make sleeve fills a clean extension of the single
    ledger-update path rather than a divergent copy.
- Estimate: **L\*** — gated by the A/B decision ([D3](decisions.md#d3)); under the DB rewrite (B),
  2a/2b/2c are built once on the clean schema instead of migrated incrementally.
- Code areas that will change:
  - 2a: new `src/trading/services/execution/` submission service; refactor
    `src/trading/services/auto_trading/runtime.py` (the inline `_run_sleeve_mode_for_account` loop and
    `_broker_aware_record_trade`) and `auto_trading/execution.py` `run_for_account` to call it, with an
    injected on-fill handler (`record_trade` vs `apply_sleeve_fill`) and the pre-submit safety gates
    (`sleeves/risk_gate.py`, reconciliation, kill switches) folded in; bridge `broker_orders` /
    `sleeve_orders` repositories.
  - 2b: unify rotation across `domain/rotation.py` + `domain/sleeve_rotation.py` +
    `services/auto_trading/rotation*.py` + `services/sleeves/rotation.py` + `shadow_evaluation.py` onto
    the decision-score contract and one trading-unit paradigm (depends on 1a ✅ and D2/D3/D7).
  - 2c: unify `services/accounting` (`record_trade`) with `services/sleeves/accounting`
    (`apply_sleeve_fill`) and the `sleeve_ledger` vs account `trades` ledgers onto one path.
  - tests across `auto_trading`, `sleeves`, `accounting`.
- Done when:
  - [ ] account and sleeve modes submit orders through one submission service with one on-fill seam
  - [ ] pre-submit safety gates are shared, not asymmetric
  - [ ] rotation/selection reads the unified decision-score contract (with P2)
  - [ ] ledger updates flow through a single accounting path

#### Close the execution loop (keystone)

Priority: P1 · Committed

- Scope: make the live/paper trader actually run the strategy signal functions and the selected
  parameter sets, so the evaluate → rotate → trade loop is closed end to end.
- Why it matters: today the live/paper trade path selects trades with a legacy random/style-biased
  placeholder — an early proof-of-concept (auto-check trades + IBKR hookup) built before the
  strategy/evaluation features existed. Strategy signal functions run **only in backtests**
  (`resolve_signal` is called solely from `src/trading/backtesting/services/execution_service.py`),
  and parameter sets are never applied to signal evaluation. So rotation switches the strategy label
  and `strategy_style` bias, but the live path does not execute the selected strategy or its params.
- Current state (evidence):
  - live/paper selection: `prepare_trade_selection` → `prepare_buy_trade`/`prepare_sell_trade` →
    `auto_trading_policy.choose_buy_ticker`/`choose_side` (random or recent-return heuristic, biased
    by `strategy_style`) — no `signal_fn`.
  - signals: `resolve_signal(strategy, history, feature_history)` uses `spec.default_params` (code
    defaults), backtest-only.
  - params: `StrategyParamSetRepository` is read only for a `param_set_id` label and by the
    governance job — never fed into signal evaluation.
- Sub-features:
  - [ ] **3-E1. Run strategy signals in live/paper execution** — the runtime trade path resolves and
    evaluates the active strategy's `signal_fn` per candidate, so paper trades the strategy it is
    evaluated on. Keystone.
  - [ ] **3-E2. Apply parameter sets to signal evaluation** end-to-end (backtest + live), so
    per-account/param-set tuning is a real, data-driven lever rather than stored metadata.
- Decisions to resolve first: [D1](decisions.md#d1) — signal→selection mapping, the runtime history
  source, backtest/live parity, and param precedence.
- Estimate: **L**. Touches the core trade loop for both account and sleeve modes, adds a runtime
  history fetch, aligns backtest, and threads param resolution — plus test rewrites.
- Code areas that will change:
  - `src/trading/domain/strategy_signals.py` — add a params-accepting signal-evaluation entry
    (today `resolve_signal` uses `spec.default_params`); keep one shared eval used by backtest + live.
  - `src/trading/domain/auto_trading_policy.py` — `choose_buy_ticker` / `choose_sell_ticker` /
    `choose_side` change from random/heuristic to signal-driven selection (per D1 policy).
  - `src/trading/services/auto_trading/execution.py` — `prepare_trade_selection` /
    `prepare_buy_trade` / `prepare_sell_trade` evaluate the active strategy's signal per candidate.
  - `src/trading/services/auto_trading/runtime.py` — wire the injected `MarketDataProvider` into the
    selection path to fetch per-ticker history (`fetch_close_series`); pass feature history via the
    existing `feature_fetchers`.
  - `src/trading/services/sleeves/execution.py` — `generate_sleeve_trade_intents` uses the same
    signal path (sleeve mode shares `prepare_trade_selection`).
  - `src/trading/repositories/strategy_param_sets.py` + a new param-resolution helper — resolve
    effective params (default → account → param set) for signals. (E2)
  - `src/trading/backtesting/services/execution_service.py` — switch `resolve_signal` to the shared
    params-aware eval so backtest and live use identical params. (E2)
  - Tests: `auto_trading`, `sleeves`, `backtesting`, and `domain/strategy_signals` suites.
- Newly surfaced holes (see D1): the live path has **no per-ticker history source** today (only
  latest `prices`), and there is **no per-ticker→which-to-act-on selection policy** — both must be
  defined before E1 is implementable.
- Done when:
  - live/paper trades are driven by the active strategy's signal function
  - parameter sets flow into both backtest and live signal evaluation
  - backtest and live execute the same strategy+param decision path
  - rotation to a strategy actually changes what the trader does

#### Plug-and-play strategy & provider catalog

Priority: P6 · Committed

- Scope: make adding strategy variants and feature providers a data/contained-code change, so new
  ideas can be tried quickly.
- Direction: keep signal **primitives** as small, tested code; make strategy **definitions**
  (`{id, primitive, params, style, required_features}`) data-loaded (config/DB) instead of the
  hard-coded `STRATEGY_REGISTRY` dict. New variant/tuning = data; genuinely new logic = one new
  primitive (code) + data to expose it. No arbitrary-logic scripting DSL (safety/testability).
- Dependency: P1 (params must actually flow into signals for data-defined variants to mean
  anything).
- Sub-features:
  - [ ] **4a. Data-driven strategy registry** — load strategy definitions from config/DB against a
    code primitive catalog; `available_strategy_ids()` and rotation read the data-defined set.
  - [ ] **4b. Feature-provider registry** — pluggable registration so a new
    `ExternalFeatureProvider` is a contained code addition + data enable.
- Estimate: **L** (4a data-driven registry ≈ M, 4b provider registry ≈ M).
- Code areas that will change:
  - 4a: `src/trading/domain/strategy_signals.py` — split into a code **primitive catalog** (signal-fn
    map) + a loader that builds `StrategySpec`s from data definitions; `STRATEGY_REGISTRY` /
    `resolve_strategy` / `available_strategy_ids` read the data-defined set. Catalog source is config
    or a `strategies` table (ties to [D5](decisions.md#d5) and the DB rewrite).
  - 4b: `src/infrastructure/feature_providers/` + a provider registry (`provider_key` → class) with
    interface-layer wiring reading enabled providers from data; shared contracts stay in
    `src/trading/domain/feature_provider.py`.
  - `src/trading/repositories/strategy_param_sets.py` referencing strategies by id; tests.
- Done when:
  - a new strategy variant of existing logic can be added without code changes
  - a new feature provider is a contained, registered addition
  - data-defined strategies flow into rotation candidates automatically

#### Notification expansion beyond webhook-only

Priority: P8 · Committed (independent)

- Scope: keep the webhook path and add optional email delivery for runtime events.
- Surface: `src/trading/interfaces/runtime/` (notifications are webhook-only today in
  `notifications.py`) and runtime job scripts.
- Decisions to resolve first: where SMTP config and recipients live (`operational_settings` vs env
  vs `account_profiles`), and whether email is filterable by event class
  (failure/recovery/success) independently of the webhook.
- Cleanup opportunity: generalize the transport-specific `notify_webhook_best_effort` into a
  `notify_runtime_event` dispatcher that fans out to a list of transports, so the three call sites
  (`reporting.py`, `trader_health.py`, `jobs/daily/paper_trading/__init__.py`) stay
  transport-agnostic.
- Estimate: **M**.
- Code areas that will change: `src/trading/interfaces/runtime/notifications.py` (add SMTP transport;
  generalize `notify_webhook_best_effort` → a `notify_runtime_event` dispatcher); SMTP config source
  ([D8](decisions.md#d8)); the three call sites (`jobs/daily/paper_trading/reporting.py`,
  `jobs/daily/trader_health.py`, `jobs/daily/paper_trading/__init__.py`); tests with a fake SMTP.
- Done when:
  - runtime jobs can emit to webhook and/or email
  - trigger classes are explicit (failure, recovery, optional success)
  - delivery failures are non-fatal and observable in logs/tests

#### Unified parameter source

Priority: P7 · Committed

- Scope: one legible place to view and edit the parameters that drive strategy behavior,
  evaluation, and rotation — supporting the goal of tuning the automated trader without hunting
  across the codebase.
- Motivation: parameters are currently scattered across ~5 locations with no single view —
  `StrategyParamSetRepository` (versioned strategy params), `src/trading/services/operational_settings/`
  (evaluation confidence, promotion policy, trade throttles), `SleeveRotationConfig` code defaults
  (rotation weights), `src/infrastructure/config/account_profiles/*.json`, and account DB columns
  (risk policy, stops, `learning_enabled`, rotation schedule/lookback/cooldown).
- Decisions to resolve first: which parameters are operator-tunable at runtime vs. code-owned
  defaults; whether the single source is a read-through view/API over the existing stores or a
  consolidated store; and how versioning/auditing works for changes.
- Estimate: **L** (shape-dependent; heavy overlap with the DB rewrite `parameters` table).
- Code areas that will change: a new parameter service (extend
  `src/trading/services/operational_settings/` or a new `services/parameters/`); a store or
  read-through view over the ~5 existing sources ([D4](decisions.md#d4)); a CLI to view/edit; migrate
  account config columns + `global_settings` + `SleeveRotationConfig` defaults over time. Sequence with
  the DB rewrite.
- Done when:
  - operator-tunable parameters are viewable and editable through one service, usable from the CLI
    and runtime without the UI (UI is an optional view over the same service)
  - rotation/evaluation weights are no longer buried as code-only defaults where they should be tunable
  - parameter changes are audited consistently

#### True adaptive learning

Priority: P10 · Exploratory

- Scope: persisted learned state and governed updates with explicit downstream effects.
- Surface: `src/trading/domain`, runtime execution, evaluation/promotion flows.
- Status today: `learning_enabled` only toggles heuristic exploration inside trade selection; there
  is no persisted learned state.
- Hard dependency: the unified decision-score contract (1a/1b). Do not design the update policy
  until a canonical score exists to learn against.
- Decisions to resolve first: what learned state is (per-strategy / per-account /
  regime-conditioned), the deterministic update policy, and the explicit downstream effects on
  ranking and eligibility.
- Estimate: **L** (deferred; design-heavy).
- Code areas (sketch): `src/trading/domain` (deterministic update policy), a learned-state store
  (DB — ties to [D6](decisions.md#d6)/rewrite), runtime execution hooks, and evaluation/promotion
  integration. Mostly TBD until [D9](decisions.md#d9) is defined.
- Done when:
  - learned state is stored, versioned, and replayable
  - update policy is deterministic and test-covered
  - ranking/trade/live-eligibility effects are explicit and observable

#### Portfolio-level risk rollup

Priority: P9 · Committed

- Scope: cross-account risk visibility, split by data dependency. The deliverable is the aggregation
  service (usable from CLI/runtime); a dashboard view is an optional follow-on.
- Surface: `src/trading/` aggregation service; optional `apps/paper_trading_web` view.
- Sub-features:
  - [ ] **2a. Exposure rollup (v1)** — cross-account equity, cash, and market-value aggregate.
    Data already exists in equity snapshots; low risk, read-only.
  - [ ] **2b. Overlap & concentration** — symbol-level cross-account analysis. Needs holdings
    aggregation across accounts and a definition decision first (concentration by symbol, sector,
    or strategy).
- Estimate: **M** (2a ≈ S, 2b ≈ M).
- Code areas that will change: a new cross-account aggregation service in `src/trading/services/`
  (exposure from `equity_snapshots` + positions); a CLI entry; optional `apps/paper_trading_web` view.
  2b needs holdings aggregation across accounts and a concentration definition
  ([D10](decisions.md#d10)); tests validating the math.
- Done when:
  - the aggregation service returns exposure and overlap/concentration payloads, usable from the CLI
    without the UI, with tests validating the math
  - an optional dashboard view renders them once the payload contract is stable

#### Strategy parameter optimization workflow

Priority: P11 · Exploratory

- Scope: dedicated optimization runs and storage, separated from regular backtests.
- Surface: `src/trading/backtesting/` services/repositories + reporting surfaces.
- Decisions to resolve first: search method (grid / random / embedded walk-forward) and the
  overfitting guardrails (mandatory OOS/walk-forward validation before a param_set is promotable).
- Sub-features:
  - [ ] **3a. Tagged optimization storage** — mark runs as optimization vs validation so
    optimization results cannot leak into promotion evidence. Foundational guardrail; land first.
  - [ ] **3b. Optimization engine + reporting** — the parameter sweeps plus a report surface that
    visually distinguishes optimization from ordinary validation runs.
- Estimate: **L** (3a ≈ S–M, 3b ≈ L).
- Code areas that will change: `src/trading/backtesting/` repositories (tag runs
  optimization-vs-validation — a `backtest_runs` flag/column or a new table) plus the evaluation
  guardrail so `services/evaluation/evidence.py` never reads optimization runs; an optimization engine
  reusing the backtest engine over param-set sweeps; reporting surfaces. Guardrails per
  [D11](decisions.md#d11).
- Done when:
  - optimization runs are tagged and stored separately (3a)
  - reports clearly distinguish optimization vs ordinary validation runs (3b)

#### Decisioning legibility & naming pass

Priority: P5 · Committed

- Scope: make the decision flow (evidence → score → promotion/rotation) legible from the package and
  symbol names, without changing behavior.
- Motivation: the current naming does not reveal the flow. Concrete offenders:
  - `shadow_evaluation` names a separate challenger-scoring path that no longer exists after P2b
    (both incumbent and challengers now score through the decision-score contract) — it is now a
    thin candidate-enumeration step and a rename/absorb candidate.
  - "rotation" means two different things (account-episode rotation vs sleeve champion/challenger) —
    disambiguate.
  - `evaluation`, `promotion`, `analysis/performance`, and `reporting` crowd the same
    "how did it do" space with unclear boundaries.
- Direction: keep evaluation, promotion, and rotation as small SRP pieces, but make them share the
  one decision-score contract and sit under a legible "decisioning" grouping so the relationship is
  obvious. This is behavior-preserving structure/naming work, best done alongside the
  [Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md) 2b step.
- Boundary to preserve: feature providers (news/sentiment) are strategy-signal inputs, not
  evaluation evidence — their effect reaches evaluation only through realized paper/live P&L. Do not
  fold them into the evaluation artifact.
- Estimate: **M** (behavior-preserving rename/restructure).
- Code areas that will change: rename/absorb `src/trading/services/sleeves/shadow_evaluation.py`;
  disambiguate the two "rotation" concepts across `domain/rotation.py` vs `domain/sleeve_rotation.py`
  and `services/auto_trading/rotation*.py` vs `services/sleeves/rotation.py`; clarify the
  evaluation/promotion/analysis/reporting grouping; update imports/tests/docs. Best done with 2b.
  Specifics in [D13](decisions.md#d13).
- Done when:
  - the decision flow is derivable from package/symbol names
  - "rotation" is unambiguous at the name level
  - `shadow_evaluation` is renamed or absorbed

## Notes

- **Holistic restructure review (pending).** After this per-item gap pass (estimates + code areas),
  step back and look at the whole picture for a larger restructure. The DB rewrite fork
  ([D3](decisions.md#d3)) is the big lever — under it, several items (P4, the P7 parameter store,
  parts of P6) may be built once on the clean schema rather than incrementally, which would
  reorder and resize this plan. Keep an open mind for bigger changes; decide the fork before
  committing to the incremental estimates above.
- Multi-universe support is already partially present (`--tickers-file`,
  `--universe-history-dir`); richer UX can wait until higher-priority slices land.
- Keep live activation explicitly human-gated.

### Design principles

- **Interface primacy: scheduler jobs and the CLI are the primary drivers; the UI is optional.**
  Core logic lives in `src/trading/` (services/domain) and every capability must be usable from the
  scheduler and CLI without the UI. The UI (`apps/paper_trading_web`) is a thin, optional consumer
  that views results and edits parameters over the same services — never the place a capability
  lives. Do not design around the UI. This is the existing "UI Backend Boundary Rule" in
  `docs/architecture/architecture-conventions.md`, applied as a product principle.
- **UI follows the contract, per feature.** Convergence and decisioning work is contract-preserving
  (no UI change — proven in 1a, which kept the compare/promotion JSON keys stable). For
  operator-facing features, the "done when" is the service + CLI/programmatic path; the UI slice is
  an optional follow-on designed *after* that feature's backend contract stabilizes, not batched to
  the end and not designed on unsettled contracts. Whether the eventual operator surface is a new
  consolidated console or incremental additions to the existing tabs is an open decision, premature
  until the parameter-source and risk contracts exist.

## Dropped (reviewed 2026-07-01)

Items removed from the active backlog during the 2026-07-01 review. Recorded so they
are not silently re-added without a fresh decision.

- **Trends workflow integration into API/UI** — `apps/trends/` remains a standalone CLI;
  integrating it into `apps/paper_trading_web` is not a current goal.
- **Non-proxy alternative data expansion** — ETF-proxy feature providers
  (`src/infrastructure/feature_providers/`) are sufficient for now; no evidence yet
  justifies the added complexity.
- **Native `IbApiClient` path** — the active IBKR integration is the Client Portal /
  Web API client; the legacy socket path (`src/infrastructure/brokers/legacy/ib_client.py`)
  stays as documented stubs and is not planned for implementation.
