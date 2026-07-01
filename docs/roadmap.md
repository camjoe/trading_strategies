# Product Roadmap

Type: notes
Status: Active
Created: 2026-06-29
Last Reviewed: 2026-06-29
Purpose: Single living backlog of outstanding product improvements — partials to finish and Now/Next/Later work — each pointing at the code it touches.
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

- **Unified evaluation** — promotion (`src/trading/services/promotion/assessment.py`) and
  reporting (`src/trading/services/reporting/presentation.py`) read the canonical evaluation
  artifact, but sleeve rotation (`src/trading/services/sleeves/rotation.py`) still scores on
  return-based metrics and compare surfaces do not expose canonical score/confidence. See
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
- Dependencies: shared scoring adapter from the evaluation artifact to rotation/compare consumers.
- Done when:
  - rotation scoring reads canonical evaluation data rather than separate return-only paths
  - compare surfaces expose canonical score/confidence fields
  - promotion, rotation, and compare are backed by one scoring contract
  - regression tests cover score usage across all three surfaces

#### 2. Portfolio-level risk dashboard v1

- Scope: cross-account risk rollup (exposure, overlap, concentration).
- Surface: `src/trading/` aggregation service + `apps/paper_trading_web` API/view.
- Dependencies: shared account snapshot/position aggregation endpoint.
- Done when:
  - backend returns aggregate exposure, overlap, and concentration payloads
  - UI renders a dedicated portfolio-risk section with these metrics
  - tests validate payload math and UI rendering

### Next

#### 1. Notification expansion beyond webhook-only

- Scope: keep the webhook path and add optional email delivery for runtime events.
- Surface: `src/trading/interfaces/runtime/` (notifications are webhook-only today in
  `notifications.py`) and runtime job scripts.
- Dependencies: email transport configuration and event routing policy.
- Done when:
  - runtime jobs can emit to webhook and/or email
  - trigger classes are explicit (failure, recovery, optional success)
  - delivery failures are non-fatal and observable in logs/tests

#### 2. Trends workflow integration into API/UI

- Scope: expose selected `apps/trends/` outputs and add a dedicated dashboard surface.
- Surface: `apps/paper_trading_web` backend/frontend, with `apps/trends/` as data source.
- Dependencies: stable API contract for trend outputs consumed by UI.
- Done when:
  - backend route returns trend-series payloads needed by UI
  - UI has a dedicated trends view using those payloads
  - tests cover contract shape and rendering

### Later

#### 1. True adaptive learning

- Scope: persisted learned state and governed updates with explicit downstream effects.
- Surface: `src/trading/domain`, runtime execution, evaluation/promotion flows.
- Dependency: completion of the unified evaluation contract in `Now`.
- Done when:
  - learned state is stored, versioned, and replayable
  - update policy is deterministic and test-covered
  - ranking/trade/live-eligibility effects are explicit and observable

#### 2. Non-proxy alternative data expansion

- Scope: selective move beyond ETF-proxy signals where evidence justifies complexity.
- Surface: `src/infrastructure/feature_providers/` and dependent strategies.
- Dependency: data quality and operational reliability criteria.
- Done when:
  - provider reliability and fallback behavior meet defined thresholds
  - strategies show measurable value vs proxy baseline in backtest/paper evidence

#### 3. Strategy parameter optimization workflow

- Scope: dedicated optimization runs and storage, separated from regular backtests.
- Surface: `src/trading/backtesting/` services/repositories + reporting surfaces.
- Dependency: guardrails to avoid overfitting and result misuse.
- Done when:
  - optimization runs are tagged and stored separately
  - reports clearly distinguish optimization vs ordinary validation runs

#### 4. Native `IbApiClient` path (optional)

- Scope: implement the native `ibapi` backend path if that backend is chosen.
- Surface: `src/infrastructure/brokers/legacy/` — the `IbApiClient` scaffold exists in
  `ib_client.py` today, but every method raises `NotImplementedError`.
- Dependency: explicit decision to operate on `ibapi` instead of `ib_async`.
- Done when:
  - the `ibapi` path reaches feature parity required for target runtime flows
  - safety and failure-mode tests pass for live guardrails

## Notes

- Multi-universe support is already partially present (`--tickers-file`,
  `--universe-history-dir`); richer UX can wait until higher-priority slices land.
- Keep live activation explicitly human-gated.
