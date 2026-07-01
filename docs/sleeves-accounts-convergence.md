# Sleeves & Accounts Convergence Plan

Type: plan
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: Living implementation and progress tracker for converging the parallel account-mode and
sleeve-mode trading paths onto shared, single-responsibility services — so behavior, safety, and
scoring are consistent and the test/paper/live environments require minimal per-path change.
Related: [Roadmap Now #2](roadmap.md#2-converge-accounts-and-sleeves-on-shared-services),
[Roadmap Now #1](roadmap.md#1-unify-evaluation-across-decision-surfaces),
[Architecture Conventions](architecture/architecture-conventions.md),
[ADR 003 — Sleeve Virtualization](adr/003-sleeve-virtualization-architecture.md),
[Broker Integration](reference/broker-integration.md)

## Goal

Accounts and sleeves currently run through two parallel orchestration paths that re-implement the
same trade lifecycle differently. Converge them onto shared services so that:

- one code path submits orders, persists broker orders, and updates the ledger (differing only by a
  small injected seam per mode);
- pre-submit safety is uniform (no path is missing a kill switch the other has);
- rotation/selection scores from one canonical contract;
- adding or changing an execution environment (test/UI sim, IBKR paper, future live) stays a
  small, modular change.

## Guiding principles

1. **Incremental and opportunistic.** Build each shared service as roadmap work touches that code;
   migrate the account and sleeve paths one seam at a time. No big-bang rewrite of the hot,
   safety-critical live path.
2. **Safety only strengthens.** When paths merge, the stricter path's guards become the shared
   default — never remove a kill switch to make merging easier.
3. **Honor the existing seams.** The `BrokerConnection` port + `get_broker_for_account` factory and
   the `live_trading_enabled` guard already converge the environment axis. Keep new code using the
   injected `broker_factory`; never construct brokers inline.
4. **SRP per service.** Each shared service owns one responsibility (submission, rotation/selection,
   accounting). Mode-specific behavior enters through explicit injected handlers, not branches.

## Scope

**In scope (accounts-vs-sleeves axis):**

- `src/trading/services/auto_trading/` (account + sleeve orchestration in `runtime.py`, `execution.py`)
- `src/trading/services/sleeves/`
- `src/trading/services/accounting/`
- The rotation modules across `auto_trading/` and `sleeves/` (and their `domain/` counterparts)

**Out of scope (already converged — do not re-litigate here):**

- The environment axis (test/UI paper sim vs IBKR paper vs live). This is handled behind
  `trading.domain.broker_connection.BrokerConnection`, `infrastructure/brokers/factory.py`, and the
  `live_trading_enabled` safety guard. A new environment = one adapter + one factory branch. Track
  broker-adapter work under the roadmap/broker docs, not here.

## Current-state map (evidence)

Confirmed by reading `src/trading/services/auto_trading/runtime.py`,
`src/trading/services/auto_trading/execution.py`, `src/trading/services/sleeves/*`, and
`src/infrastructure/brokers/factory.py` on 2026-07-01.

| Concern | Account mode | Sleeve mode | Status |
|---|---|---|---|
| Broker resolution | injected `broker_factory` → `get_broker_for_account` | same | ✅ already shared |
| Trade selection | `prepare_trade_selection` (`auto_trading/execution.py`) | `generate_sleeve_trade_intents` → also `prepare_trade_selection` | ✅ already shared |
| Order submission + broker-order persistence | `_broker_aware_record_trade` closure (`runtime.py`) | inline loop in `_run_sleeve_mode_for_account` (`runtime.py`) | ❌ duplicated |
| On-fill ledger update | `record_trade` | `apply_sleeve_fill` + `record_trade` | ❌ divergent |
| Pre-submit safety gates | throttles only | kill switches: stale price, reconciliation mismatch/staleness | ❌ asymmetric |
| Rotation / selection | account episode rotation | sleeve champion/challenger | ❌ two paradigms |
| Scoring metrics | daily-metrics-derived | backtest-returns-derived (challengers) + `StrategyEvaluationArtifact` | ❌ three notions (see Roadmap Now #1) |
| Reconciliation | `reconcile_open_broker_orders` | `reconcile_sleeves_vs_latest_snapshot` | ⚠️ to investigate |
| Account/equity state | `refresh_account_state` → `compute_account_state` | `_build_sleeve_state` (from sleeve positions) | ⚠️ to investigate |
| Risk snapshots | (none) | `portfolio_risk_snapshots` + `sleeve_risk_decisions` | ⚠️ to investigate |
| Order repositories | `broker_orders` | `broker_orders` + `sleeve_orders` | ⚠️ to investigate |
| Intent model | selection tuple `(side, ticker, qty, ...)` | `SleeveTradeIntent` dataclass | ⚠️ to investigate |

Legend: ✅ already converged · ❌ confirmed duplication/divergence · ⚠️ candidate, not yet deeply verified.

## Workstreams

### Confirmed (roadmap Now #2 sub-features)

- [ ] **2a. Shared order-submission service**
  - Extract "submit intent → persist broker order → on-fill ledger update" into one service
    (e.g. `src/trading/services/execution/`) called by both modes.
  - Difference between modes enters only via an injected on-fill handler (account ledger vs sleeve
    ledger) and an injected order-persistence seam (`broker_orders` vs `broker_orders` + `sleeve_orders`).
  - Fold the pre-submit safety gates in so the account path inherits the sleeve kill switches.
  - Highest-value slice; directly reduces future live-path risk.
- [ ] **2b. Unified rotation/selection**
  - Collapse account episode rotation and sleeve champion/challenger onto the Now #1 decision-score
    contract; reduce the rotation module sprawl (`auto_trading/rotation.py`, `runtime_rotation.py`,
    `rotation_bridge.py`, `sleeves/rotation.py`, `shadow_evaluation.py`).
  - **Depends on Roadmap Now #1a** (shared decision-score contract).
- [ ] **2c. Unified accounting/ledger path**
  - Make sleeve fills a clean extension of the single ledger-update path rather than a divergent copy
    of `record_trade`.

### To investigate (add findings, then promote to a workstream or close out)

- [ ] Reconciliation: are `reconcile_open_broker_orders` and `reconcile_sleeves_vs_latest_snapshot`
  two aspects of one reconciliation concern, or genuinely distinct (open-order polling vs
  equity-tolerance guard)?
- [ ] State/equity: can account and sleeve state derivation share a computation, or is sleeve state
  intentionally position-scoped?
- [ ] Risk snapshots: should account mode gain an equivalent of the sleeve risk snapshot /
  decisions, or is that intrinsically a sleeve concept?
- [ ] Order repositories: is `sleeve_orders` a necessary extension of `broker_orders`, or can it be
  a linked detail table behind one submission service?
- [ ] Intent model: is a shared trade-intent contract worthwhile, or does `SleeveTradeIntent` stay
  a sleeve-specific superset?

## Dependencies & sequencing

- **1a → 1b and 2b.** The shared decision-score contract (Roadmap Now #1a) unblocks both the
  rotation migration (1b) and the unified rotation/selection here (2b).
- **2a is independent.** The broker seam is already clean, so the submission-service extraction can
  start immediately without waiting on the scoring work.
- Suggested order: **2a** (safety + biggest duplication) → **2c** (ledger) alongside 2a → **2b**
  once 1a lands.

## Open questions

- Package/name for the shared submission service (`services/execution/` vs extending
  `services/auto_trading/`).
- Whether the shared submission service should own the pre-submit safety gates directly, or accept
  them as an injected policy so sleeve-specific gates stay pluggable.
- How far to unify the order-persistence tables vs keep `sleeve_orders` as a mode-specific detail.

## Progress log

- 2026-07-01 — Document created. Captured current-state map, confirmed 2a/2b/2c workstreams,
  investigation candidates, and sequencing. Environment axis confirmed already converged and marked
  out of scope. (Elaboration to follow.)
