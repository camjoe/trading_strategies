# Product Roadmap

Type: notes
Status: Active
Created: 2026-06-29
Last Reviewed: 2026-07-01
Purpose: Single living backlog and progress tracker for outstanding product improvements — partials to finish and Now/Next/Later work — each pointing at the code it touches.
Related: [Docs Map](maps/docs-map.md), [Trading Package Map](maps/trading-package-map.md), [UI Map](maps/ui-map.md)

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
  [Now #1](#1-unify-evaluation-across-decision-surfaces).
- **`learning_enabled`** — active as heuristic exploration (account-profile flag in
  `src/infrastructure/config/account_profiles/*.json` plus a DB column), but with no persisted,
  versioned learned state. See [Later #1](#1-true-adaptive-learning).

## Now / Next / Later

Time windows:

- `Now`: next implementation cycle (start immediately)
- `Next`: follow-on work after `Now` ships
- `Later`: defer until higher-priority operational value is complete

### Current cycle sequencing

The two `Now` initiatives interlock. Recommended order for this cycle:

1. **1a — decision-score contract.** Self-contained; touches evaluation code only. No entanglement
   with the sleeves-accounts convergence and no rework risk from the virtual-vs-table-rework (A/B)
   decision — safe to build regardless of how that lands.
2. **1b — rotation scoring repoint (narrow).** Make the incumbent and challengers score from the
   same source via the 1a contract, leaving the two rotation paradigms in place. This is the first
   time evaluation work edits sleeve rotation code but still needs no A/B decision.
3. **1c — contract regression tests** across compare, promotion, and rotation.

**Decision gate — end of 1b.** With scoring unified you will be standing in the rotation code. Decide
then whether to cross into the convergence work (2b paradigm collapse, then 2a/2c). Going past narrow
1b into 2b forces resolving the trading-unit stance and the A/B realization — see
[Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md). Until that gate, keep 1b
narrow and leave the convergence details deferred.

### Now

#### 1. Unify evaluation across decision surfaces

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
- Done when:
  - [x] compare surfaces expose canonical score/confidence fields
  - [ ] a single decision-score contract backs compare, promotion, and rotation (1a)
  - [ ] rotation scoring reads the contract rather than separate return-only paths, with incumbent
    and challengers scored from the same source (1b)
  - [ ] regression tests cover score usage across all three surfaces (1c)

#### 2. Converge accounts and sleeves on shared services

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
    same root cause as Now #1.
- Sub-features (independent; each migrates account + sleeve one seam at a time):
  - [ ] **2a. Shared order-submission service** — extract "submit intent → persist broker order →
    on-fill ledger update" into one service (e.g. `src/trading/services/execution/`) that both modes
    call, differing only by an injected on-fill handler (account ledger vs sleeve ledger). Fold the
    pre-submit safety gates in so account mode inherits the sleeve kill switches. Highest-value slice
    and directly reduces live-path risk.
  - [ ] **2b. Unified rotation/selection** — collapse account episode rotation and sleeve
    champion/challenger onto the Now #1 decision-score contract, and reduce the rotation module
    sprawl. Depends on Now #1a.
  - [ ] **2c. Unified accounting/ledger path** — make sleeve fills a clean extension of the single
    ledger-update path rather than a divergent copy.
- Done when:
  - [ ] account and sleeve modes submit orders through one submission service with one on-fill seam
  - [ ] pre-submit safety gates are shared, not asymmetric
  - [ ] rotation/selection reads the unified decision-score contract (with Now #1)
  - [ ] ledger updates flow through a single accounting path

### Next

#### 1. Notification expansion beyond webhook-only

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
- Done when:
  - runtime jobs can emit to webhook and/or email
  - trigger classes are explicit (failure, recovery, optional success)
  - delivery failures are non-fatal and observable in logs/tests

#### 2. Unified parameter source

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
- Done when:
  - operator-tunable parameters are viewable and editable through one service, usable from the CLI
    and runtime without the UI (UI is an optional view over the same service)
  - rotation/evaluation weights are no longer buried as code-only defaults where they should be tunable
  - parameter changes are audited consistently

### Later

#### 1. True adaptive learning

- Scope: persisted learned state and governed updates with explicit downstream effects.
- Surface: `src/trading/domain`, runtime execution, evaluation/promotion flows.
- Status today: `learning_enabled` only toggles heuristic exploration inside trade selection; there
  is no persisted learned state.
- Hard dependency: the unified decision-score contract (Now #1a/1b). Do not design the update policy
  until a canonical score exists to learn against.
- Decisions to resolve first: what learned state is (per-strategy / per-account /
  regime-conditioned), the deterministic update policy, and the explicit downstream effects on
  ranking and eligibility.
- Done when:
  - learned state is stored, versioned, and replayable
  - update policy is deterministic and test-covered
  - ranking/trade/live-eligibility effects are explicit and observable

#### 2. Portfolio-level risk rollup

- Scope: cross-account risk visibility, split by data dependency. The deliverable is the aggregation
  service (usable from CLI/runtime); a dashboard view is an optional follow-on.
- Surface: `src/trading/` aggregation service; optional `apps/paper_trading_web` view.
- Sub-features:
  - [ ] **2a. Exposure rollup (v1)** — cross-account equity, cash, and market-value aggregate.
    Data already exists in equity snapshots; low risk, read-only.
  - [ ] **2b. Overlap & concentration** — symbol-level cross-account analysis. Needs holdings
    aggregation across accounts and a definition decision first (concentration by symbol, sector,
    or strategy).
- Done when:
  - the aggregation service returns exposure and overlap/concentration payloads, usable from the CLI
    without the UI, with tests validating the math
  - an optional dashboard view renders them once the payload contract is stable

#### 3. Strategy parameter optimization workflow

- Scope: dedicated optimization runs and storage, separated from regular backtests.
- Surface: `src/trading/backtesting/` services/repositories + reporting surfaces.
- Decisions to resolve first: search method (grid / random / embedded walk-forward) and the
  overfitting guardrails (mandatory OOS/walk-forward validation before a param_set is promotable).
- Sub-features:
  - [ ] **3a. Tagged optimization storage** — mark runs as optimization vs validation so
    optimization results cannot leak into promotion evidence. Foundational guardrail; land first.
  - [ ] **3b. Optimization engine + reporting** — the parameter sweeps plus a report surface that
    visually distinguishes optimization from ordinary validation runs.
- Done when:
  - optimization runs are tagged and stored separately (3a)
  - reports clearly distinguish optimization vs ordinary validation runs (3b)

#### 4. Decisioning legibility & naming pass

- Scope: make the decision flow (evidence → score → promotion/rotation) legible from the package and
  symbol names, without changing behavior.
- Motivation: the current naming does not reveal the flow. Concrete offenders:
  - `shadow_evaluation` names a separate challenger-scoring path that no longer exists after Now #1b
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
- Done when:
  - the decision flow is derivable from package/symbol names
  - "rotation" is unambiguous at the name level
  - `shadow_evaluation` is renamed or absorbed

## Notes

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
  (no UI change — proven in Now #1a, which kept the compare/promotion JSON keys stable). For
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
