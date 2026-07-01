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

## Design stance: unify at the trading-unit level

The organizing model for this convergence is a **composite**, aligned with ADR 003:

- **Account = custody/broker aggregate root.** Owns the broker connection, the `live_trading_enabled`
  safety gate, and reconciliation-to-broker-truth. These are account-scoped and stay there.
- **Sleeve = the trading unit.** Owns cash, positions, ledger, and strategy/param-set assignment —
  the primitive that accounting, submission attribution, and rotation/selection operate on.
- **A plain account is one account with a single default trading unit** spanning the whole balance.

Under this model the shared services (2a/2b/2c) do not special-case "account mode vs sleeve mode";
they operate on one **trading-unit contract**, and account mode is just the default unit. This is a
refinement of — not a replacement for — the 2a/2b/2c workstreams: it names the contract they share.

Consistent with ADR 003: accounts stay broker/custody entities (Decision #1), sleeve attribution
reconciles to account truth (Decision #4), and the account submission/reconciliation flow is the
reuse base with attribution lifted to unit-aware persistence (Reuse #3). Note the account cannot
literally *be* a sleeve: broker + `live_trading_enabled` + reconciliation-to-truth are genuinely
account-scoped and must not be pushed onto a sleeve.

### Realization options (open decision)

The default trading unit can be modeled two ways:

- **(A) Virtual default unit — current short-term lean.** The trading-unit contract has two backings
  (sleeve-backed and account-backed); a plain account presents a *synthesized* default unit over the
  existing account tables. No migration of the hot ledger/positions/orders tables. Costs a small
  amount of polymorphism (two backings) in exchange for keeping account semantics unchanged. Matches
  ADR Reuse #3.
- **(B) Physical table rework.** Give every account a real default trading-unit row and reparent
  ledger/positions/orders onto units. Purest single-backing model, but a backfill on the most
  safety-critical tables. Because we are **not yet live production**, there is a genuine window to
  re-evaluate whether the current tables meet our needs and, if so, do this rework before that window
  closes. Higher up-front risk/effort; cleanest end state.

**Decision status:** leaning (A) virtual short-term to unblock convergence without a hot-table
migration. Keep (B) open: schedule a deliberate pre-live table review and decide before live
enablement, when schema changes are cheapest. Do not commit 2a/2c to a specific persistence shape
until this is settled.

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
| Scoring metrics | account-episode rotation still separate | incumbent + challengers via the decision-score contract (Now #1b) | ◑ sleeve side unified (1b); account rotation pending 2b |
| Reconciliation | `reconcile_open_broker_orders` | `reconcile_sleeves_vs_latest_snapshot` | ⚠️ to investigate |
| Account/equity state | `refresh_account_state` → `compute_account_state` | `_build_sleeve_state` (from sleeve positions) | ⚠️ to investigate |
| Risk snapshots | (none) | `portfolio_risk_snapshots` + `sleeve_risk_decisions` | ⚠️ to investigate |
| Order repositories | `broker_orders` | `broker_orders` + `sleeve_orders` | ⚠️ to investigate |
| Intent model | selection tuple `(side, ticker, qty, ...)` | `SleeveTradeIntent` dataclass | ⚠️ to investigate |

Legend: ✅ already converged · ◑ partially converged · ❌ confirmed duplication/divergence · ⚠️ candidate, not yet deeply verified.

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
  - Post-1b, `shadow_evaluation` is a thin candidate-enumeration step — its separate challenger
    scoring path is gone, so it is a rename/absorb candidate. The behavior-preserving naming work
    (rename `shadow_evaluation`, disambiguate the two "rotation" meanings, clarify the
    evaluation/promotion/analysis/reporting boundaries) is tracked as Roadmap Later #4
    (Decisioning legibility & naming pass) and is best done alongside this step.
  - Keep evaluation, promotion, and rotation as small SRP pieces that share the one decision-score
    contract under a legible "decisioning" grouping — not a monolith.
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
- [ ] Order repositories: under the trading-unit stance, `broker_orders` stays broker/custody truth
  and unit attribution links to it. Provisional direction is to bridge `sleeve_orders` behind the
  submission service rather than merge tables; the final shape depends on realization (A) vs (B).
- [ ] Intent model: the trading-unit stance favors a shared trade-intent contract (the account
  selection tuple becomes the default-unit intent); confirm scope when 2a lands.

## Dependencies & sequencing

- **1a → 1b and 2b.** The shared decision-score contract (Roadmap Now #1a) unblocks both the
  rotation migration (1b) and the unified rotation/selection here (2b).
- **1b checkpoint (entry point to this plan).** Narrow 1b (repoint rotation scoring onto the 1a
  contract, both paradigms intact) needs neither the trading-unit stance nor the A/B decision. The
  end of 1b is the natural gate for deciding whether to cross into this convergence work: going past
  narrow 1b into 2b forces resolving the design stance (A vs B). Until then these workstreams stay
  deferred.
- **2a is independent.** The broker seam is already clean, so the submission-service extraction can
  start immediately without waiting on the scoring work.
- Suggested order: **2a** (safety + biggest duplication) → **2c** (ledger) alongside 2a → **2b**
  once 1a lands.

## Open questions

- **Realization: virtual default unit (A) vs physical table rework (B)** — see Design stance.
  Leaning (A) short-term; revisit (B) in a pre-live table review before live enablement. This gates
  the persistence shape for 2a/2c.
- Package/name for the shared submission service (`services/execution/` vs extending
  `services/auto_trading/`).
- Whether the shared submission service should own the pre-submit safety gates directly, or accept
  them as an injected policy so sleeve-specific gates stay pluggable.
- Order-persistence shape depends on the realization decision above: under (A), bridge
  `broker_orders`/`sleeve_orders` behind the submission service; under (B), reparent onto units.

## Progress log

- 2026-07-01 — Document created. Captured current-state map, confirmed 2a/2b/2c workstreams,
  investigation candidates, and sequencing. Environment axis confirmed already converged and marked
  out of scope.
- 2026-07-01 — Added "unify at the trading-unit level" design stance (account = custody root
  containing trading units; a plain account is one default unit), aligned with ADR 003. Recorded
  virtual (A) vs physical-table-rework (B) as an open realization decision; current lean is virtual
  short-term, with a pre-live table review to revisit (B). Updated open questions and investigation
  items accordingly.
- 2026-07-01 — Now #1b landed: sleeve rotation now scores incumbent + challengers through the
  decision-score contract (current-state "Scoring metrics" row now partial). Marked
  `shadow_evaluation` as a rename/absorb candidate under 2b and recorded the decisioning
  legibility/naming direction (tracked as Roadmap Later #4). Added the Roadmap Next item for a
  unified parameter source (param sprawl across ~5 stores).
