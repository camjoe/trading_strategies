# Sleeves & Accounts Convergence Plan

Type: plan
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: Living implementation and progress tracker for converging the parallel account-mode and
sleeve-mode trading paths onto shared, single-responsibility services — so behavior, safety, and
scoring are consistent and the test/paper/live environments require minimal per-path change.
Related: [Plan — Converge accounts & sleeves (P4)](plan.md#converge-accounts-and-sleeves-on-shared-services),
[Plan — Unify evaluation (P2)](plan.md#unify-evaluation-across-decision-surfaces),
[Architecture Conventions](architecture/architecture-conventions.md),
[ADR 003 — Sleeve Virtualization](adr/003-sleeve-virtualization-architecture.md),
[Broker Integration](reference/broker-integration.md)

> **Realized via the rewrite.** With rewrite-first chosen ([D2/D3](decisions.md#d2)), convergence is
> **built once on the clean book schema** during Plan P3 (rewrite) → P4 (services), not by
> incrementally migrating two live paths. This doc is the **design reference** for the converged
> services; the schema itself is in the [DB Schema Rewrite Spec](db-schema-rewrite-spec.md). The
> current-state map below documents the duplication the rewrite removes.

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

1. **Build once on the clean schema.** With the greenfield rewrite chosen (P3), the shared services
   are built directly on the clean strategy-book tables (P4) — one submission/rotation/accounting path
   — rather than migrating two live paths incrementally. There is no live data to protect
   (greenfield), which is what makes the clean build the low-risk option.
2. **Safety only strengthens.** When paths merge, the stricter path's guards become the shared
   default — never remove a kill switch to make merging easier.
3. **Honor the existing seams.** The `BrokerConnection` port + `get_broker_for_account` factory and
   the `live_trading_enabled` guard already converge the environment axis. Keep new code using the
   injected `broker_factory`; never construct brokers inline.
4. **SRP per service.** Each shared service owns one responsibility (submission, rotation/selection,
   accounting). Mode-specific behavior enters through explicit injected handlers, not branches.

## Design stance: unify at the strategy-book level

The organizing model for this convergence is a **composite**, aligned with ADR 003:

- **Account = custody/broker aggregate root.** Owns the broker connection, the `live_trading_enabled`
  safety gate, and reconciliation-to-broker-truth. These are account-scoped and stay there.
- **Sleeve = the strategy book.** Owns cash, positions, ledger, and strategy/param-set assignment —
  the primitive that accounting, submission attribution, and rotation/selection operate on.
- **A plain account is one account with a single default strategy book** spanning the whole balance.

Under this model the shared services (2a/2b/2c) do not special-case "account mode vs sleeve mode";
they operate on one **strategy-book contract**, and account mode is just the default book. This is a
refinement of — not a replacement for — the 2a/2b/2c workstreams: it names the contract they share.

Consistent with ADR 003: accounts stay broker/custody entities (Decision #1), sleeve attribution
reconciles to account truth (Decision #4), and the account submission/reconciliation flow is the
reuse base with attribution lifted to book-aware persistence (Reuse #3). Note the account cannot
literally *be* a sleeve: broker + `live_trading_enabled` + reconciliation-to-truth are genuinely
account-scoped and must not be pushed onto a sleeve.

### Realization options (decided: B)

The default strategy book was modeled two ways; **(B) was chosen** (see Decision status below):

- **(A) Virtual default book — rejected.** The strategy-book contract has two backings
  (sleeve-backed and account-backed); a plain account presents a *synthesized* default book over the
  existing account tables. No migration of the hot ledger/positions/orders tables. Costs a small
  amount of polymorphism (two backings) in exchange for keeping account semantics unchanged. Matches
  ADR Reuse #3.
- **(B) Physical table rework.** Give every account a real default strategy-book row and reparent
  ledger/positions/orders onto books. Purest single-backing model. Because we are **not yet live
  production** and are willing to drop existing data, this is a **greenfield schema init with no data
  migration** — which removes the backfill risk that would otherwise dominate. A concrete target
  schema is drafted in the [Database Schema Rewrite — Spec](db-schema-rewrite-spec.md); adopting it
  is this option. Cleanest end state; larger up-front build, but it collapses much of 2a/2b/2c into
  "build once on the new schema."

**Decision status (2026-07-01): (B) chosen** — the greenfield rewrite
([D2](decisions.md#d2)/[D3](decisions.md#d3)/[D7](decisions.md#d7)). Convergence (2a/2b/2c) is built
**once on the clean schema** (P4), after the execution loop (P1) and the rewrite (P3), rather than
migrating two live paths incrementally. See the
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md).

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
| Scoring metrics | account-episode rotation still separate | incumbent + challengers via the decision-score contract (1b) | ◑ sleeve side unified (1b); account rotation pending 2b |
| Reconciliation | `reconcile_open_broker_orders` | `reconcile_sleeves_vs_latest_snapshot` | ⚠️ to investigate |
| Account/equity state | `refresh_account_state` → `compute_account_state` | `_build_sleeve_state` (from sleeve positions) | ⚠️ to investigate |
| Risk snapshots | (none) | `portfolio_risk_snapshots` + `sleeve_risk_decisions` | ⚠️ to investigate |
| Order repositories | `broker_orders` | `broker_orders` + `sleeve_orders` | ⚠️ to investigate |
| Intent model | selection tuple `(side, ticker, qty, ...)` | `SleeveTradeIntent` dataclass | ⚠️ to investigate |

Legend: ✅ already converged · ◑ partially converged · ❌ confirmed duplication/divergence · ⚠️ candidate, not yet deeply verified.

## Workstreams

### Confirmed (P4 sub-features)

- [ ] **2a. Shared order-submission service**
  - Extract "submit intent → persist broker order → on-fill ledger update" into one service
    (for example, a future `trading.services.execution` package) called by both modes.
  - On the clean schema there is one `orders`/`order_fills`/`ledger` model keyed by strategy book, so
    "modes" collapse to the default-book vs multi-book case — no per-mode persistence branching.
  - The one path owns the pre-submit safety gates (kill switches, reconciliation), so every book
    inherits them uniformly.
  - Highest-value slice; directly reduces future live-path risk.
- [ ] **2b. Unified rotation/selection**
  - Collapse account episode rotation and sleeve champion/challenger onto the P2 decision-score
    contract; reduce the rotation module sprawl (`auto_trading/rotation.py`, `runtime_rotation.py`,
    `rotation_bridge.py`, `sleeves/rotation.py`, `shadow_evaluation.py`).
  - Post-1b, `shadow_evaluation` is a thin candidate-enumeration step — its separate challenger
    scoring path is gone, so it is a rename/absorb candidate. The behavior-preserving naming work
    (rename `shadow_evaluation`, disambiguate the two "rotation" meanings, clarify the
    evaluation/promotion/analysis/reporting boundaries) is tracked as Plan P5
    (Decisioning legibility & naming pass) and is best done alongside this step.
  - Keep evaluation, promotion, and rotation as small SRP pieces that share the one decision-score
    contract under a legible "decisioning" grouping — not a monolith.
  - **Depends on Plan 1a** (shared decision-score contract).
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
- [x] Order repositories: resolved by the rewrite — one `orders`/`order_fills` model keyed by book;
  `broker_order_id` keeps custody linkage. No bridging of two tables.
- [x] Intent model: resolved — one trade-intent contract on the strategy book (the account selection
  tuple becomes the default-book intent).

## Dependencies & sequencing

- **Sequenced by the plan:** P1 (execution loop) → P2 (1c) → **P3 (rewrite)** → **P4 (these services,
  built once on the clean schema)**, with P5 (naming) alongside. See [plan.md](plan.md).
- **1a/1b are done** — the decision-score contract already backs sleeve rotation; 2b builds on it.
- Within P4, suggested internal order: **2a** (submission service + safety gates) → **2c** (ledger)
  → **2b** (unified rotation/selection).

## Open questions

Canonical decision status in [decisions.md](decisions.md). Remaining design detail:

- **Which rotation paradigm survives on books** — account-episode vs champion/challenger. The
  champion/challenger model + the decision-score contract is the developed path; **leaning
  champion/challenger** (recorded in the P4 work order §5); confirm and retire the episode path
  during 2b.
- ~~Package/name for the shared submission service~~ — **decided (2026-07-05): new
  `services/execution/` package** (SRP; keeps `auto_trading/` orchestration-focused).
- ~~Gate ownership~~ — **decided (2026-07-05): injected pre-submit gate policy**, not hard-coded, so
  book/environment-specific gates stay pluggable and unit-testable.

Work order: [implementation/p4-convergence.md](implementation/p4-convergence.md) (2a phased in full;
2c/2b sketched).

## Progress log

- 2026-07-01 — Document created. Captured current-state map, confirmed 2a/2b/2c workstreams,
  investigation candidates, and sequencing. Environment axis confirmed already converged and marked
  out of scope.
- 2026-07-01 — Added "unify at the strategy-book level" design stance (account = custody root
  containing strategy books; a plain account is one default book), aligned with ADR 003. Recorded
  virtual (A) vs physical-table-rework (B) as an open realization decision; current lean is virtual
  short-term, with a pre-live table review to revisit (B). Updated open questions and investigation
  items accordingly.
- 2026-07-01 — 1b landed: sleeve rotation now scores incumbent + challengers through the
  decision-score contract (current-state "Scoring metrics" row now partial). Marked
  `shadow_evaluation` as a rename/absorb candidate under 2b and recorded the decisioning
  legibility/naming direction (tracked as Plan P5). Added the P7 item for a
  unified parameter source (param sprawl across ~5 stores).
- 2026-07-01 — Drafted the [Database Schema Rewrite — Spec](db-schema-rewrite-spec.md) concretizing
  realization option (B). Reframed (B) as greenfield (no data migration, old data dropped), which
  removes the backfill risk and means adopting the spec collapses much of 2a/2b/2c into a
  build-once-on-clean-schema effort. Realization decision (A vs B) remains open.
- 2026-07-01 — Rewrite-first (B) decided. Reframed this plan from incremental migration to
  "build the converged services once on the clean schema" (P3 → P4): updated guiding principles,
  the workstream persistence framing, sequencing, and open questions; resolved the order-repository
  and intent-model investigations (one `orders`/`ledger`/`positions` model on books). Flagged the
  surviving-rotation-paradigm question.
- 2026-07-05 — P3 complete (clean book schema + repositories live, reads re-pointed via
  `book_bridge`; the clean `orders`/`order_fills`/`positions`/`ledger` tables exist but are empty —
  2a is their first writer). P4 started: resolved the two submission-service open questions (new
  `services/execution/` package; injected pre-submit gate policy) and wrote the phased
  [P4 work order](implementation/p4-convergence.md) with 2a detailed (2a-1 service in isolation →
  2a-2 gate → 2a-3 account cutover → 2a-4 sleeve cutover + reconciliation re-point → 2a-5 retire
  legacy writers). Noted the reconciliation coupling: `reconcile_open_broker_orders` reads
  `broker_orders`/`sleeve_orders` and must move to clean `orders` in lockstep with the cutover.
- 2026-07-05 — 2a-1 landed: the `trading.services.execution` package now exists in isolation (no
  caller wired). `submit_book_intents` runs the injected gate → per approved intent `broker.place_order`
  → persists the clean book-keyed `orders`/`order_fills`, and on a filled order updates `positions` +
  appends a single `ledger` `trade` entry — the first writer of those tables. Added the passive
  `BookTradeIntent`/`GateResult`/`SubmissionResult` contracts (`models/execution/`), the `PreSubmitGate`
  protocol + `AllowAllGate`, and `OrderRepository.insert_fill` (order_id-keyed). Broker-API exceptions
  append the `broker_api_anomaly` kill switch and stop, mirroring the legacy sleeve loop. Fill math
  reuses the domain `apply_sleeve_fill_transition` (book-agnostic; folds broker commission + configured
  fee into cost basis). Unit tests cover fill / hold / partial / broker-exception / gate-block /
  gate-kill-switch / sell / on-fill. Next: 2a-2 (production gate).
