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
| [D1](#d1) | Execution-loop signal/param mapping | Now #3 | open (near-term) |
| [D2](#d2) | Convergence realization: virtual (A) vs physical rework (B) | Now #2, DB rewrite | leaning A (short-term) |
| [D3](#d3) | Incremental convergence vs DB-rewrite-first | Now #2 approach & timelines | open (pivotal) |
| [D4](#d4) | Parameters model shape | Next #2, DB rewrite | open |
| [D5](#d5) | Strategy catalog granularity | Now #4, DB rewrite | open |
| [D6](#d6) | Persist evaluation/decision snapshots? | Later #1, auditability | open |
| [D7](#d7) | Default trading unit: real row vs virtual | Now #2, DB rewrite | leaning real (under rewrite) |
| [D8](#d8) | Email notifications config | Next #1 | open |
| [D9](#d9) | Adaptive-learning definition | Later #1 | deferred |
| [D10](#d10) | Portfolio-risk concentration definition | Later #2b | deferred |
| [D11](#d11) | Param-optimization method & guardrails | Later #3 | deferred |
| [D12](#d12) | Operator UI surface: console vs incremental tabs | operator-facing UI | deferred (premature) |
| [D13](#d13) | Decisioning naming/grouping specifics | Later #4 | deferred |

Near-term to resolve: **D1** (unblocks the keystone), and **D2/D3** (gate the whole convergence
approach and its timelines).

---

<a id="d1"></a>
### D1 — Execution-loop signal/param mapping

Gates: Plan Now #3 (close the execution loop). **Open, near-term.**

The backtest model to mirror ([`backtesting/services/execution_service.py`](../src/trading/backtesting/services/execution_service.py)):
per ticker in the universe, `history = close.loc[:signal_date, ticker]` → `resolve_signal(strategy,
history, feature_history)` → act on buy/sell/hold. Live should evaluate the same way.

- **Runtime history source.** Live selection today receives only latest `prices` (a dict), not the
  per-ticker `pd.Series` history signals need. Decide how the runtime fetches history —
  `MarketDataProvider.fetch_close_series(ticker, period)` exists and `run_for_account` already accepts
  an injectable `provider`; decide period/lookback, caching, and per-run cost across the universe.
- **Selection policy.** `signal_fn` yields buy/sell/hold *per ticker*, but the live loop currently
  picks one ticker via `min_trades/max_trades`. Decide how per-ticker signals map to "which tickers
  to act on this run" (all buy-signaled subject to cash/sizing, like backtest? capped? ranked how?).
- **Sizing/risk mapping.** How signal output feeds the existing `choose_buy_qty`, forced-sell, and
  sleeve risk-gate flow.
- **Backtest/live parity.** Ensure both call one shared signal+param evaluation path so backtest
  evidence reflects live behavior.
- **Param precedence.** Where resolved params come from — param set vs account override vs strategy
  default — and the precedence order.

<a id="d2"></a>
### D2 — Convergence realization: virtual (A) vs physical rework (B)

Gates: Plan Now #2 persistence shape, DB rewrite. **Leaning A short-term; B open pre-live.**

Virtual default unit over existing tables (A) vs a physical table rework with a real default unit
(B). See the [convergence realization options](sleeves-accounts-convergence.md) and the
[DB rewrite spec](db-schema-rewrite-spec.md). Related to D3 and D7.

<a id="d3"></a>
### D3 — Incremental convergence vs DB-rewrite-first (pivotal)

Gates: Plan Now #2 approach and its timelines. **Open.**

If we adopt B (the DB rewrite), do we **skip the incremental 2a/2b/2c** and build the shared
submission/rotation/accounting once on the clean schema, rather than migrating two live paths
first? This choice reshapes the order and estimates of a large block of work. Since we can drop old
data (greenfield), B's historical risk is low — so this is genuinely open.

<a id="d4"></a>
### D4 — Parameters model shape

Gates: Plan Next #2 (unified parameter source), DB rewrite (`parameters` table). **Open.**

- Typed key/value rows with scope precedence (default → account → unit) vs a few typed config tables
  per concern (risk / options / rotation).
- Read-through view/API over existing stores vs a consolidated store.
- Versioning/audit of changes.
- Which parameters are operator-tunable at runtime vs code-owned defaults.

<a id="d5"></a>
### D5 — Strategy catalog granularity

Gates: Plan Now #4 (plug-and-play), DB rewrite (`strategies` table). **Open.**

Does a `strategies` row capture only (primitive + defaults), with variants living entirely in
`strategy_param_sets`, or can a strategy row itself pin a specific param set?

<a id="d6"></a>
### D6 — Persist evaluation/decision snapshots?

Gates: Later #1 (adaptive learning), auditability. **Open.**

Store the decision score at rotation/promotion time (aids audit + future versioned learned state) vs
keep evaluation purely derived. Storage cost vs replayability.

<a id="d7"></a>
### D7 — Default trading unit: real row vs virtual

Gates: Plan Now #2, DB rewrite. **Leaning real row (under a rewrite).**

A rewrite makes a real default-unit row natural and cheap (no backfill). Tied to D2/D3.

<a id="d8"></a>
### D8 — Email notifications config

Gates: Plan Next #1. **Open.**

Where SMTP config and recipients live (`operational_settings` vs env vs `account_profiles`), and
whether email is filterable by event class (failure/recovery/success) independently of the webhook.

<a id="d9"></a>
### D9 — Adaptive-learning definition

Gates: Plan Later #1. **Deferred** (depends on the decision-score contract).

What learned state is (per-strategy / per-account / regime-conditioned), the deterministic update
policy, and the explicit downstream effects on ranking and eligibility.

<a id="d10"></a>
### D10 — Portfolio-risk concentration definition

Gates: Plan Later #2b. **Deferred.**

Concentration measured by symbol, sector, or strategy.

<a id="d11"></a>
### D11 — Param-optimization method & guardrails

Gates: Plan Later #3. **Deferred.**

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

Gates: Plan Later #4 (decisioning legibility & naming pass). **Deferred.**

Rename target for `shadow_evaluation`, how to disambiguate the two "rotation" meanings, and the
"decisioning" grouping for evaluation/promotion/rotation.
