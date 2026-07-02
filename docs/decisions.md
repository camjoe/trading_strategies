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
| [D4](#d4) | Parameters model shape | parameter source, DB rewrite | **partly decided** |
| [D5](#d5) | Strategy catalog granularity | plug-and-play, DB rewrite | **decided: primitive + knobs** |
| [D6](#d6) | Persist evaluation/decision snapshots? | adaptive learning, auditability | open |
| [D7](#d7) | Default trading unit: real row vs virtual | P4, DB rewrite | **decided: real row (under B)** |
| [D8](#d8) | Email notifications config | P8 | open |
| [D9](#d9) | Adaptive-learning definition | P10 | deferred |
| [D10](#d10) | Portfolio-risk concentration definition | P9 | deferred |
| [D11](#d11) | Param-optimization method & guardrails | P11 | deferred |
| [D12](#d12) | Operator UI surface: console vs incremental tabs | operator-facing UI | deferred (premature) |
| [D13](#d13) | Decisioning naming/grouping specifics | P5 | deferred |

Decided so far: **D1** (trade policy), **D2/D3/D7** (rewrite-first), **D5** (strategy = primitive +
knobs), **D4** (params split: knobs in strategy rows, settings on account/unit — a few sub-points
still open). Remaining rewrite-detail: the account/unit settings shape (D4 tail) and **D6** (persist
decision snapshots). D8–D13 stay deferred.

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

Gates: Plan P7 (unified parameter source), DB rewrite. **Partly decided (2026-07-01).**

Two kinds of "parameters", stored in two places:

- **Strategy knobs** (fast/slow windows, RSI thresholds) → **decided:** live inside the strategy row
  (see [D5](#d5)). The separate `strategy_param_sets` table is **dropped**.
- **Account/execution settings** (risk policy, stop-loss, position sizing, max-trades-per-run,
  rotation cooldown, instrument/option config) → live on the **account / trading-unit**, no longer in
  a 50-column god-table.
- **Unified parameter source (P7)** = a service/CLI **view** over strategy rows (knobs) + account/unit
  settings + a few global settings — not a new consolidated store.

Still open (settle during the rewrite): whether account/unit settings are typed columns vs a small
typed config table per concern; and the change-audit approach for account/unit settings.

<a id="d5"></a>
### D5 — Strategy catalog granularity

Gates: Plan P6 (plug-and-play), DB rewrite (`strategies` table). **Decided (2026-07-01).**

A **strategy = a code primitive + its knobs**, stored as one data row:
`{ id, name, primitive, params_json (knobs), style, required_features, enabled, status }`. Variants
are **new rows** using the same primitive with different knobs. The **primitive** (the signal
function + its knob schema) stays in code; the strategy row is data, so new variants are added
without code.

- **Versioning / tuning — decided:** a strategy is **fixed once it has backtest evidence or is live**;
  tuning creates a **new** strategy row (old + new both persist → automatic history, replacing the
  param-set table's purpose). Draft strategies (no evidence yet) are freely editable.
- Accounts/units and rotation reference strategies **by id**; `strategy_param_sets`, `param_set_id`
  columns, and per-assignment param sets are removed.

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
