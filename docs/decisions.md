# Open Decisions — What Needs Defining

Type: notes
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: The single consolidated list of decisions that must be made before or during implementation
— "what needs to be defined." Tasks/order/status live in [plan.md](plan.md); design detail lives in
the referenced specs.
Related: [Plan](plan.md), [Overview](overview.md),
[Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md),
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md)

Status legend: **open** (undecided) · **leaning** (tentative direction) · **deferred** (not needed
yet) · **decided** (resolved — record the outcome and date).

## Summary

| ID | Decision | Gates | Status |
|---|---|---|---|
| [D1](#d1) | Execution-loop signal/param mapping | P1 | **mostly resolved** (defaults recorded) |
| [D2](#d2) | Convergence realization: virtual (A) vs physical rework (B) | P4, DB rewrite | **decided: B (rewrite)** |
| [D3](#d3) | Incremental convergence vs DB-rewrite-first | convergence approach & timelines | **decided: rewrite-first, after execution loop** |
| [D4](#d4) | Parameters model shape | parameter source, DB rewrite | open |
| [D5](#d5) | Strategy catalog granularity | plug-and-play, DB rewrite | open |
| [D6](#d6) | Persist evaluation/decision snapshots? | adaptive learning, auditability | open |
| [D7](#d7) | Default trading unit: real row vs virtual | P4, DB rewrite | **decided: real row (under B)** |
| [D8](#d8) | Email notifications config | P8 | open |
| [D9](#d9) | Adaptive-learning definition | P10 | deferred |
| [D10](#d10) | Portfolio-risk concentration definition | P9 | deferred |
| [D11](#d11) | Param-optimization method & guardrails | P11 | deferred |
| [D12](#d12) | Operator UI surface: console vs incremental tabs | operator-facing UI | deferred (premature) |
| [D13](#d13) | Decisioning naming/grouping specifics | P5 | deferred |

Near-term to resolve: **D1** (unblocks the keystone). **D2/D3/D7 are now decided** (rewrite-first);
next definition work is **D4** (parameters) and **D5** (strategy catalog), both needed for the DB
rewrite.

---

<a id="d1"></a>
### D1 — Execution-loop signal/param mapping

Gates: Plan P1 (close the execution loop). **Mostly resolved; implementation defaults recorded.**

The backtest model to mirror ([`backtesting/services/execution_service.py`](../src/trading/backtesting/services/execution_service.py)):
per ticker in the universe, `history = close.loc[:signal_date, ticker]` → `resolve_signal(strategy,
history, feature_history)` → act on buy/sell/hold. Live should evaluate the same way.

- **Selection policy — decided (2026-07-01).** Trade **only when the strategy signals** — act on the
  stocks it labels buy (not already held) and sell (held). **No forced minimum** (remove today's
  min-trades floor that manufactures trades when nothing signals). **Keep a maximum cap** per run so
  an account/unit can't over-trade. In plain terms: never trade out of "nervousness," but bound the
  number of trades.
- **Param source — deferred to the rewrite.** P1 will read strategy knobs from the account/defaults
  and **will not depend on the `strategy_param_sets` table**. Whether tunable knobs live on the
  account/unit or in a param-set table is decided with the schema rewrite — see [D4](#d4).
- **Runtime history source — default.** Fetch per-ticker history via
  `MarketDataProvider.fetch_close_series(ticker, period)` (already injectable into `run_for_account`),
  a fixed lookback (~1y, covering the largest indicator window), cached per run. Implementation
  detail, revisit only if cost is a problem.
- **Backtest/live parity — default.** Both paths call one shared
  `evaluate_signal(strategy, history, params, feature_history)` so backtest evidence reflects live
  behavior.
- **Sizing/risk mapping — default.** Signal output feeds the existing `choose_buy_qty`, forced-sell,
  and sleeve risk-gate flow unchanged.

<a id="d2"></a>
### D2 — Convergence realization: virtual (A) vs physical rework (B)

Gates: convergence persistence shape, DB rewrite. **Decided (2026-07-01): B — the physical
greenfield rewrite.** No data to lose and pre-live is the cheapest time to change schema, so the
clean rework wins over carrying the virtual two-backing approach. Related to D3 and D7.

<a id="d3"></a>
### D3 — Incremental convergence vs DB-rewrite-first (pivotal)

Gates: convergence approach and timelines. **Decided (2026-07-01): rewrite-first.** Sequence:
close the execution loop (P1, schema-agnostic) → finish evaluation tests (P2) → DB rewrite (P3) →
build the shared submission/rotation/accounting **once** on the clean schema (P4), rather than
migrating two live paths first. Avoids building convergence twice; leverages the empty greenfield.

<a id="d4"></a>
### D4 — Parameters model shape

Gates: Plan P7 (unified parameter source), DB rewrite (`parameters` table). **Open.**

- **Do we keep `strategy_param_sets` at all?** (Raised 2026-07-01.) The named/versioned param-set
  table is currently empty and unused. Option: put tunable strategy knobs directly on the
  account/trading-unit (simpler), and only reintroduce a param-set table if/when sharing across
  accounts or auto-optimization (P11) actually needs it. Decide with the rewrite.
- Typed key/value rows with scope precedence (default → account → unit) vs a few typed config tables
  per concern (risk / options / rotation).
- Read-through view/API over existing stores vs a consolidated store.
- Versioning/audit of changes.
- Which parameters are operator-tunable at runtime vs code-owned defaults.

<a id="d5"></a>
### D5 — Strategy catalog granularity

Gates: Plan P6 (plug-and-play), DB rewrite (`strategies` table). **Open.**

Does a `strategies` row capture only (primitive + defaults), with variants living entirely in
`strategy_param_sets`, or can a strategy row itself pin a specific param set?

<a id="d6"></a>
### D6 — Persist evaluation/decision snapshots?

Gates: P10 (adaptive learning), auditability. **Open.**

Store the decision score at rotation/promotion time (aids audit + future versioned learned state) vs
keep evaluation purely derived. Storage cost vs replayability.

<a id="d7"></a>
### D7 — Default trading unit: real row vs virtual

Gates: convergence, DB rewrite. **Decided (2026-07-01): real default-unit row**, following the
rewrite decision (D2/D3) — cheap under greenfield, cleanest single-backing model.

<a id="d8"></a>
### D8 — Email notifications config

Gates: Plan P8. **Open.**

Where SMTP config and recipients live (`operational_settings` vs env vs `account_profiles`), and
whether email is filterable by event class (failure/recovery/success) independently of the webhook.

<a id="d9"></a>
### D9 — Adaptive-learning definition

Gates: Plan P10. **Deferred** (depends on the decision-score contract).

What learned state is (per-strategy / per-account / regime-conditioned), the deterministic update
policy, and the explicit downstream effects on ranking and eligibility.

<a id="d10"></a>
### D10 — Portfolio-risk concentration definition

Gates: Plan P9. **Deferred.**

Concentration measured by symbol, sector, or strategy.

<a id="d11"></a>
### D11 — Param-optimization method & guardrails

Gates: Plan P11. **Deferred.**

Search method (grid / random / embedded walk-forward) and the overfitting guardrails (mandatory
OOS/walk-forward validation before a param set is promotable).

<a id="d12"></a>
### D12 — Operator UI surface: console vs incremental tabs

Gates: operator-facing UI features. **Deferred (premature).**

Whether the eventual operator surface is a new consolidated console or incremental additions to the
existing `apps/paper_trading_web` tabs. Premature until the parameter-source and risk contracts
exist.

<a id="d13"></a>
### D13 — Decisioning naming/grouping specifics

Gates: Plan P5 (decisioning legibility & naming pass). **Deferred.**

Rename target for `shadow_evaluation`, how to disambiguate the two "rotation" meanings, and the
"decisioning" grouping for evaluation/promotion/rotation.
