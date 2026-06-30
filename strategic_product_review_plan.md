# Strategic Product Plan (Consolidated)

Purpose: keep one short, current planning document for the trading project.

This document should represent the current product reality and the highest-value next work.

Last reviewed: 2026-04-24

---

## Product Goal

Keep the system simple, robust, and evidence-driven while supporting:

- multiple strategy families
- continuous comparison and rotation
- controlled use of external signals
- explicit paper-to-live promotion gates

---

## Current State Snapshot

### Stable and implemented

- multi-strategy backtesting and walk-forward workflows
- paper trading with snapshots, trades, and account-level benchmark overlays
- persisted promotion review workflow with append-only audit history
- scheduled daily backtest refresh job with idempotency/retry/artifacts
- guarded live-broker path with explicit live activation controls

### Important partials

- canonical evaluation artifact exists and is used for promotion/readiness and reporting summaries
- rotation strategy selection still uses separate return-based logic instead of a single unified evaluation pipeline
- `learning_enabled` now changes runtime selection behavior, but remains heuristic-only (no persisted learned model/state)

### Still open

- no dedicated trends dashboard that directly exposes the `trends/` workflow in the UI
- no portfolio-level aggregate risk dashboard (cross-account exposure/overlap/concentration)
- runtime notifications are primarily webhook-based; no first-class email notification path

---

## Relevance Audit of Prior Plan

### Still relevant

- keep live execution explicitly gated
- keep overlays conservative and interpretable
- unify comparison, rotation, and promotion around one canonical evaluation model

### Needs wording updates

- prior note that `learning_enabled` was not active is outdated
- better framing: it is active heuristic exploration, but not a true adaptive learner

### Stale and removed

- references to `local/implementation_roadmap.md` and `local/implementation_roadmap_reconciled.md` (not present)
- backlog items that imply missing baseline capabilities already delivered (promotion persistence, scheduled refresh, walk-forward detail, benchmark overlays)

---

## Now / Next / Later

Time windows:

- `Now`: next implementation cycle (start immediately)
- `Next`: follow-on work after `Now` ships
- `Later`: defer until higher-priority operational value is complete

### Now

#### 1. Unify evaluation across decision surfaces

- Scope: one canonical evaluation output drives compare, rotation selection, and promotion decisions.
- Surface: `trading`, `paper_trading_ui` (backend + frontend compare/admin views).
- Dependencies: shared scoring adapter from evaluation artifact to rotation/compare consumers.
- Done when:
  - rotation scoring reads canonical evaluation data rather than separate return-only scoring paths
  - compare surfaces expose canonical score/confidence fields
  - promotion, rotation, and compare are backed by one scoring contract
  - regression tests cover score usage across all three surfaces

#### 2. Portfolio-level risk dashboard v1

- Scope: cross-account risk rollup (exposure, overlap, concentration).
- Surface: `trading` aggregation service + `paper_trading_ui` API/view.
- Dependencies: shared account snapshot/position aggregation endpoint.
- Done when:
  - backend returns aggregate exposure, overlap, and concentration payloads
  - UI renders a dedicated portfolio-risk section with these metrics
  - tests validate payload math and UI rendering

### Next

#### 1. Notification expansion beyond webhook-only

- Scope: keep webhook path and add optional email delivery for runtime events.
- Surface: `trading/interfaces/runtime` and runtime job scripts.
- Dependencies: email transport configuration and event routing policy.
- Done when:
  - runtime jobs can emit to webhook and/or email
  - trigger classes are explicit (failure, recovery, optional success)
  - delivery failures are non-fatal and observable in logs/tests

#### 2. Trends workflow integration into API/UI

- Scope: expose selected `trends/` outputs and add a dedicated dashboard surface.
- Surface: `paper_trading_ui` backend/frontend, with `trends/` as data source.
- Dependencies: stable API contract for trend outputs consumed by UI.
- Done when:
  - backend route returns trend-series payloads needed by UI
  - UI has a dedicated trends view using those payloads
  - tests cover contract shape and rendering

### Later

#### 1. True adaptive learning

- Scope: persisted learned state and governed updates with explicit downstream effects.
- Surface: `trading/domain`, runtime execution, evaluation/promotion flows.
- Dependency: completion of unified evaluation contract in `Now`.
- Done when:
  - learned state is stored, versioned, and replayable
  - update policy is deterministic and test-covered
  - ranking/trade/live-eligibility effects are explicit and observable

#### 2. Non-proxy alternative data expansion

- Scope: selective move beyond ETF-proxy signals where evidence justifies complexity.
- Surface: `trading/features` and dependent strategies.
- Dependency: data quality and operational reliability criteria.
- Done when:
  - provider reliability and fallback behavior meet defined thresholds
  - strategies show measurable value vs proxy baseline in backtest/paper evidence

#### 3. Strategy parameter optimization workflow

- Scope: dedicated optimization runs and storage, separated from regular backtests.
- Surface: `trading/backtesting` services/repositories + reporting surfaces.
- Dependency: guardrails to avoid overfitting and result misuse.
- Done when:
  - optimization runs are tagged and stored separately
  - reports clearly distinguish optimization vs ordinary validation runs

#### 4. Native `IbApiClient` path (optional)

- Scope: implement native `ibapi` backend path if that backend is chosen.
- Surface: `trading/brokers/legacy`.
- Dependency: explicit decision to operate on `ibapi` instead of `ib_async`.
- Done when:
  - `ibapi` path reaches feature parity required for target runtime flows
  - safety and failure-mode tests pass for live guardrails

Notes:

- multi-universe support is already partially present (`--tickers-file`, `--universe-history-dir`); richer UX can wait until higher-priority slices land
- keep live activation explicitly human-gated
