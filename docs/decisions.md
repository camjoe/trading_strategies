# Open Decisions — What Needs Defining

Type: notes
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-03
Purpose: The single consolidated list of decisions that must be made before or during implementation
— "what needs to be defined." Current status lives in [status.md](status.md); design detail lives in
the referenced specs.
Related: [Status](status.md), [Overview](overview.md),
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md)

Status legend: **open** (undecided) · **leaning** (tentative direction) · **deferred** (not needed
yet) · **decided** (resolved — record the outcome and date).

## Summary

| ID | Decision | Gates | Status |
|---|---|---|---|
| [D1](#d1) | Execution-loop signal/param mapping | P1 | **mostly resolved** (defaults recorded) |
| [D2](#d2) | Convergence realization: virtual (A) vs physical rework (B) | P4, DB rewrite | **decided: B (rewrite)** |
| [D3](#d3) | Incremental convergence vs DB-rewrite-first | convergence approach & timelines | **decided: rewrite-first, after execution loop** |
| [D4](#d4) | Parameters model shape | parameter source, DB rewrite | **decided** (settings shape 2026-07-03) |
| [D5](#d5) | Strategy catalog granularity | plug-and-play, DB rewrite | **decided: primitive + knobs** |
| [D6](#d6) | Persist evaluation/decision snapshots? | adaptive learning, auditability | **decided: score columns; table deferred** |
| [D7](#d7) | Default strategy book: real row vs virtual | P4, DB rewrite | **decided: real row (under B)** |
| [D8](#d8) | Email notifications config | P8 | **decided: env-var SMTP (2026-07-07)** |
| [D9](#d9) | Adaptive-learning definition | P10 | deferred |
| [D10](#d10) | Portfolio-risk concentration definition | P9 | deferred |
| [D11](#d11) | Param-optimization method & guardrails | P11 | deferred |
| [D12](#d12) | Operator UI surface: console vs incremental tabs | operator-facing UI | deferred (premature) |
| [D13](#d13) | Decisioning naming/grouping specifics | P5 | deferred |
| [D14](#d14) | Execution-primitive name: "book" (was "trading unit") | P3 Phase E onward | **decided: book (2026-07-04)** |

Decided: **D1** (trade policy), **D2/D3/D7** (rewrite-first), **D5** (strategy = primitive + knobs),
**D4** (params split + settings shape, 2026-07-03), **D6** (score columns; snapshot table deferred),
**D14** (execution primitive named "book", 2026-07-04), **D8** (email notifications config: env-var
SMTP, 2026-07-07). Nothing gates the rewrite anymore. **D9–D13 stay deferred** (feature-specific, not
gating the near-term plan).

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
  an account/book can't over-trade. In plain terms: never trade out of "nervousness," but bound the
  number of trades.
- **Param source — deferred to the rewrite.** P1 will read strategy knobs from the account/defaults
  and **will not depend on the `strategy_param_sets` table**. Whether tunable knobs live on the
  account/book or in a param-set table is decided with the schema rewrite — see [D4](#d4).
- **Runtime history source — default.** Fetch per-ticker history via
  `MarketDataProvider.fetch_close_series(ticker, period)` (already injectable into `run_for_account`),
  a fixed lookback (~1y, covering the largest indicator window), cached per run. Implementation
  detail, revisit only if cost is a problem.
- **Backtest/live parity — default.** Both paths call one shared
  `evaluate_signal(strategy, history, params, feature_history)` so backtest evidence reflects live
  behavior.
- **Parity nuance (recorded 2026-07-02).** The shared function gives *function* parity, not *window*
  parity: live evaluates on a fixed ~1y history while backtest history grows from the run's start
  date. Tail-window indicators (the SMA family, ≤~60-day windows) are unaffected; whole-series
  computations (e.g. MACD's EWM) can differ slightly for the same date. Accepted — a small
  backtest/live signal divergence is **not a bug**; revisit (e.g. fix one shared lookback window in
  both paths) only if it proves material.
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

Gates: Plan P7 (unified parameter source), DB rewrite. **Decided** (split 2026-07-01; settings
shape 2026-07-03).

Two kinds of "parameters", stored in two places:

- **Strategy knobs** (fast/slow windows, RSI thresholds) → **decided:** live inside the strategy row
  (see [D5](#d5)). The separate `strategy_param_sets` table is **dropped**.
- **Account/execution settings** (risk policy, stop-loss, position sizing, max-trades-per-run,
  rotation cooldown, instrument/option config) → live on the **account / strategy-book**, no longer in
  a 50-column god-table.
- **Unified parameter source (P7)** = a service/CLI **view** over strategy rows (knobs) + account/book
  settings + a few global settings — not a new consolidated store.

**Settings shape — decided (2026-07-03, start of P3 Phase A):** account/book settings live in
**small typed config tables, one per concern, keyed 1:1 to `books`**:

- `book_execution_settings` — learning flag, risk policy, stops/targets, sizing pcts,
  max-trades-per-run, instrument mode.
- `book_option_settings` — the option/leaps block (strike offset, DTE range, delta/IV bounds,
  premium/contract caps, roll threshold); a row exists only for option-capable books.
- `book_rotation_settings` — rotation enable/mode/optimality/interval/lookback/schedule, regime
  strategy references, overlay config. **Settings only** — rotation *state*
  (`rotation_active_index` / `rotation_last_at` / `rotation_active_strategy`) is not stored as
  settings; the active strategy is the open `book_strategy_assignments` row and last-rotation time
  derives from `rotation_decisions`.
- Book mandate metadata (`goal_min_return_pct` / `goal_max_return_pct` / `goal_period`) sits directly
  on `books` beside `trade_universes` — a 3-column reporting concern doesn't warrant a table.
- Missing settings row → code defaults (same fallback style as today's profile defaults).

Rationale: typed columns per concern keep the SRP win that motivated the rewrite (no re-grown
god-table), stay `CHECK`-constrainable, and give P7 an obvious per-concern read/edit surface.

**Change-audit — decided: deferred to P7.** Until the unified parameter service exists, settings
change only via seed/bootstrap CLI from git-tracked profiles; `updated_at` per settings row is
enough. P7 adds the audit log when it adds the edit surface.

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
- Accounts/books and rotation reference strategies **by id**; `strategy_param_sets`, `param_set_id`
  columns, and per-assignment param sets are removed.

<a id="d6"></a>
### D6 — Persist evaluation/decision snapshots?

Gates: P10 (adaptive learning), auditability. **Decided (2026-07-01): cheap hedge.**

Store the decision **score + confidence as first-class columns** on `rotation_decisions` (promotion
already freezes its full evaluation/assessment payloads). **No** dedicated `decision_snapshots` table
until adaptive learning (P10) is actually pursued — greenfield makes adding it later cheap. Gives a
queryable "what score did we act on" history without speculative machinery.

<a id="d7"></a>
### D7 — Default strategy book: real row vs virtual

Gates: convergence, DB rewrite. **Decided (2026-07-01): real default-book row**, following the
rewrite decision (D2/D3) — cheap under greenfield, cleanest single-backing model.

<a id="d8"></a>
### D8 — Email notifications config

Gates: Plan P8. **Decided (2026-07-07): env-var SMTP config.**

SMTP settings live in environment variables (`TRADING_RUNTIME_ALERT_SMTP_*`), mirroring the existing
webhook env pattern — no DB/schema change, and the password stays out of source by construction.
Email is fully opt-in and best-effort, fanned out alongside the webhook by `notify_runtime_event`;
auth is optional (unauthenticated relays supported). Runtime-editable recipients via
`operational_settings` (DB) were rejected for now as unneeded surface (recipients change via env +
redeploy). Email currently mirrors the webhook's event set; **per-transport event-class filtering
(failure/recovery/success independently) is deferred** until there is demand. Variables are
documented in the runtime-operations runbook.

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

<a id="d14"></a>
### D14 — Execution-primitive name: "book"

Gates: P3 Phase E onward (everything built on the clean schema). **Decided (2026-07-04): "book".**

The clean-schema execution primitive was originally named "trading unit". Renamed to **book**
before any consumer was built on it, because "unit" is overloaded in this repo (scheduler *time
units*, the money *minor-units* convention, *unit tests*) and greps poorly. "Book" is
finance-native — a trading book is exactly a bounded pool of capital run to one strategy — has
zero prior occurrences in `src/`, and gives short identifiers (`books`, `book_id`,
`book_execution_settings`). Applied across schema DDL, models (`models/books/`), repositories,
seeding, and the planning docs while the tables were still consumer-free. Alternatives considered:
reviving "sleeve" (rejected — ambiguous with the retiring legacy paradigm) and "mandate"
(rejected — longer, more abstract).
