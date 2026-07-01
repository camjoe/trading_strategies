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

#### 2. Portfolio-level risk dashboard

- Scope: cross-account risk visibility, split by data dependency.
- Surface: `src/trading/` aggregation service + `apps/paper_trading_web` API/view.
- Sub-features:
  - [ ] **2a. Exposure rollup (v1)** — cross-account equity, cash, and market-value aggregate.
    Data already exists in equity snapshots; low risk, read-only.
  - [ ] **2b. Overlap & concentration** — symbol-level cross-account analysis. Needs holdings
    aggregation across accounts and a definition decision first (concentration by symbol, sector,
    or strategy).
- Done when:
  - backend returns aggregate exposure payloads and a dedicated UI section renders them (2a)
  - backend returns overlap/concentration payloads with tests validating the math (2b)

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

## Notes

- Multi-universe support is already partially present (`--tickers-file`,
  `--universe-history-dir`); richer UX can wait until higher-priority slices land.
- Keep live activation explicitly human-gated.

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
