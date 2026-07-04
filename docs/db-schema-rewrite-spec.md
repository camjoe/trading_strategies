# Database Schema Rewrite — Spec (Draft)

Type: spec
Status: Accepted — sequenced as P3 (after the execution loop)
Created: 2026-07-01
Last Reviewed: 2026-07-03
Purpose: Target database schema aligned with the app's goals. This is the concrete form of the
convergence plan's "physical table rework (option B)", which was **chosen** on 2026-07-01
([D2](decisions.md#d2)/[D3](decisions.md#d3)): rewrite-first, after the execution loop, then build
convergence once on the clean schema. Open schema-detail decisions remain (D4, D5, D6).
Related: [Overview](overview.md), [Plan](plan.md),
[Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md),
[Architecture Conventions](architecture/architecture-conventions.md),
[DB Migration System](reference/db-migration-system.md),
[ADR 003 — Sleeve Virtualization](adr/003-sleeve-virtualization-architecture.md)

## Framing

- **This is the chosen path (option B), not yet started.** Sequenced as P3 — after the execution
  loop (P1) and evaluation tests (P2), before convergence (P4).
- **We are willing to drop existing data.** No production/live data exists yet, so the rewrite is a
  **greenfield schema init with no data migration** — the single biggest simplifier. Accounts,
  strategies, and parameters are re-created from config/CLI.
- **This is convergence "option B".** Convergence (submission/rotation/accounting) is built **once on
  the clean schema** (P4) rather than migrating two live paths incrementally.
- **When:** after the execution loop is closed (P1) and before live enablement — when schema changes
  are cheapest and the runtime behavior is known-good.
- **Runtime pause (accepted 2026-07-02):** the paper-trading scheduler jobs are paused from P3
  Phase A until P4's shared submission service lands — the old operational tables are dropped and
  the writers arrive with P4. Expected downtime, pre-live and paper-only.

## Data-loss assessment (2026-07-01)

Live DB checked: `local/paper_trading.db`. Conclusion: **nothing meaningful is lost by dropping it.**

Row counts at assessment time:

| Table | Rows | Nature |
|---|---|---|
| `promotion_reviews` / `promotion_review_events` | 0 / 0 | Human audit trail — the only genuinely non-reproducible class; **empty** |
| `rotation_decisions` / `rotation_episodes` | 0 / 0 | Autonomous-decision audit; empty |
| `strategy_param_sets` | 0 | Params not stored in the DB yet |
| `strategy_sleeves` / `sleeve_strategy_assignments` | 0 / 0 | No sleeves configured yet |
| `daily_metrics` | 0 | Derived |
| `global_settings` | 0 | Using code defaults |
| `accounts` | 8 | Config, re-choosable from profiles/CLI |
| `trades` / `broker_orders` / `equity_snapshots` | 637 / 219 / 135 | Early proof-of-concept test data (disposable) |
| `backtest_runs` | 25 | Rerunnable |

Why there is no meaningful loss:

- **Human audit trails are empty** — the one class that cannot be regenerated (promotion reviews/events) has zero rows.
- **Strategy logic is code**, not data (`STRATEGY_REGISTRY` + signal functions in `domain/strategy_signals.py`).
- **Config is in git**, not the DB (`account_profiles/*.json`, `trade_universe(s)`, `symbol_sectors.json`,
  `account_trade_caps.json`, `market_data_config`). Migrating these into new tables is a design choice, not a recovery concern.
- **Trades/orders/snapshots are disposable** early-test data; new trades are produced daily.
- **Backtests/walk-forward are rerunnable** on demand.
- **No learned state exists** yet (adaptive learning unbuilt).
- **Backups exist** in `local/db_backups/` if old test data is ever wanted for inspection.

Before dropping — see the checklist in [Developer Notes & Task Tracker](developer-notes.md):

- Confirm no promotion review history has accrued since this assessment.
- Check the 8 accounts for any parameters you actually tuned and want to keep (params were mostly
  arbitrary/profile defaults; `strategy_param_sets` is empty).
- Note broker connection config; `live_trading_enabled` must be re-set manually by design.

## Goals the schema must serve

From [overview.md](overview.md):

1. **Trading-unit model** — an account is a custody/broker root; strategy execution happens in
   trading units; a plain account is one account with a single default unit.
2. **Data-driven strategies and parameters** — strategies and parameter sets are data, so variants
   and accounts are added without code.
3. **One evidence-driven evaluation** feeding compare/rotation/promotion via the decision-score
   contract.
4. **Single parameter source** — no parameters buried in a god-table.
5. **Human-gated live** — the `live_trading_enabled` guard survives unchanged.
6. **One order/fill/position/ledger/rotation model** — no parallel account-vs-sleeve families.

## Current schema pain points (grounding — 25 tables today)

- **Parallel account-vs-unit families.** Account-level `trades`, `equity_snapshots`,
  `broker_orders` + `order_fills`, `rotation_episodes` sit alongside sleeve-level `sleeve_orders`,
  `sleeve_fills`, `sleeve_ledger`, `sleeve_positions`, `rotation_decisions`. Same concepts, twice.
- **`accounts` is a ~50-column god-table** mixing custody/broker, strategy selection, risk policy,
  ~15 `option_*` columns, ~15 `rotation_*` columns, and goals — a schema-level SRP violation and the
  root of parameter sprawl.
- **Parameters live in ≥3 places**: `accounts` columns, `strategy_param_sets`, and `global_settings`.
- **Strategy is a bare string** (`strategy_name TEXT`) everywhere — no `strategies` catalog table
  (the "strategies are code" reality at the data layer).
- **Two rotation record models** (`rotation_decisions` sleeve vs `rotation_episodes` account).
- **Snapshots split** account (`equity_snapshots`) vs unit (`strategy_sleeves.current_equity`).
- `daily_metrics` already carries an optional `sleeve_id` — a hint the unit model is half-present.

## Proposed target schema

Naming uses **trading unit** as the execution primitive. A plain account has exactly one default
unit. (Open decision below: whether the default unit is a real row or virtual.)

### Custody & units

- **`accounts`** — custody/broker only: `id`, `name`, `descriptive_name`, `base_ccy`, `initial_cash`,
  `benchmark_ticker`, broker fields (`broker_type`, `broker_host`, `broker_port`, `broker_client_id`),
  `live_trading_enabled`, timestamps. **All strategy/risk/option/rotation config leaves this table.**
- **`trading_units`** (replaces `strategy_sleeves`) — `id`, `account_id`, `name`, `status`,
  `is_default`, `start_equity`, `current_cash`, `current_equity`, `trade_universes`, timestamps.

### Strategy catalog & parameters (data-driven)

- **`strategies`** (new) — a strategy = a code **primitive** + its **knobs** (D5): `id`,
  `strategy_key`, `primitive`, `params_json` (the knobs), `style`, `required_features` (json),
  `description`, `status` (draft/frozen), `enabled`. Variants/tuning = new rows; frozen once a
  strategy has evidence or is live (automatic history). **No `strategy_param_sets` table** — its
  purpose is folded in here. Enables Plan P6 (plug-and-play).
- **Account/unit settings** (D4) — execution/risk/rotation settings (risk policy, stops, sizing,
  max-trades-per-run, rotation cooldown, instrument/option config) live on `accounts`/`trading_units`
  (not a god-table, not strategy knobs). The **unified parameter source (P7)** is a service/CLI view
  over strategy rows + account/unit settings + a few global settings. Exact settings shape (typed
  columns vs a small typed config table) is the open tail of D4.
- **`feature_providers`** (optional, new) — pluggable provider catalog: `id`, `provider_key`,
  `enabled`, `config_json`. Fetch logic stays code; enablement is data.

### Assignment & rotation (one model)

- **`unit_strategy_assignments`** (replaces `sleeve_strategy_assignments`) — `id`, `unit_id`,
  `strategy_id`, `effective_from`, `effective_to`, `is_incumbent`, timestamps. (No `param_set_id` —
  the strategy row carries its knobs.)
- **`rotation_decisions`** (unifies `rotation_decisions` + `rotation_episodes`) — keyed by `unit_id`;
  carries incumbent/challenger/selected, action, gate/score json, decision reason, config version,
  and (folding episodes) the realized-performance window fields. Adds first-class `decision_score` +
  `decision_confidence` columns (D6).

### Execution & accounting (one model, keyed by unit)

- **`orders`** (unifies `broker_orders` + `sleeve_orders`) — `id`, `unit_id`, `account_id`,
  `strategy_id`, `rotation_decision_id`, `broker_order_id`, symbol/side/qty/type/
  tif/requested_price/status/filled_qty/avg_fill_price/commission, timestamps. Broker linkage stays
  first-class (custody truth).
- **`order_fills`** (unifies `order_fills` + `sleeve_fills`) — `id`, `order_id`, `broker_fill_id`,
  `exec_id`, qty/price/commission/fill_time.
- **`positions`** (replaces `sleeve_positions`) — keyed by `(unit_id, symbol)`.
- **`ledger`** (unifies `sleeve_ledger` + account `trades`) — `id`, `unit_id`, `entry_type`, `amount`,
  `reference_type`, `reference_id`, `entry_time`. Realized-trade rows are ledger entries.
- **`equity_snapshots`** — per `unit_id`; the account view is the roll-up (sum of units). Keeps the
  reconciliation invariant explicit (sum of unit equity == broker/account truth).

### Evaluation, risk, promotion, backtesting

- **`daily_metrics`** — per `unit_id` (account view = default unit / roll-up).
- **`risk_snapshots`** + **`risk_decisions`** (from `portfolio_risk_snapshots` + `sleeve_risk_decisions`)
  — per account, referencing units; kill-switch payloads retained.
- **`promotion_reviews`** + **`promotion_review_events`** — largely as today; reference
  `strategy_id`/`unit_id`; keep the frozen assessment/evaluation payloads and append-only events.
- **Backtesting tables** (`backtest_runs`, `backtest_trades`, `backtest_equity_snapshots`,
  `walk_forward_groups`, `walk_forward_group_runs`) — structurally stable; change `strategy_name`
  string to `strategy_id` FK. Evaluation evidence continues to be assembled (not stored), optionally
  with persisted decision snapshots (open decision).

### Old → new consolidation map

| Today | Target |
|---|---|
| `strategy_sleeves` | `trading_units` |
| `sleeve_strategy_assignments` | `unit_strategy_assignments` |
| `broker_orders` + `sleeve_orders` | `orders` |
| `order_fills` + `sleeve_fills` | `order_fills` |
| `sleeve_positions` | `positions` |
| `sleeve_ledger` + `trades` | `ledger` |
| `equity_snapshots` (account) + `strategy_sleeves.current_equity` | `equity_snapshots` (per unit) + account roll-up |
| `rotation_decisions` + `rotation_episodes` | `rotation_decisions` (unit-keyed) |
| `portfolio_risk_snapshots` + `sleeve_risk_decisions` | `risk_snapshots` + `risk_decisions` |
| `accounts` risk/option/rotation columns + `global_settings` | settings on slimmed `accounts`/`trading_units` (+ `global_settings`) |
| `strategy_name` strings | `strategies` catalog (primitive + knobs) + `strategy_id` FKs |
| `strategy_param_sets` | folded into `strategies` rows (variants = new rows) |
| (none) | `feature_providers` catalog |

## What stays stable / reusable (not a rewrite)

Recent refactors mean much of the stack re-points at new repositories without redesign:

- **Broker seam** — `BrokerConnection` port + factory + `live_trading_enabled` guard, unchanged.
- **Decision-score contract** — `EvaluationDecisionScore` + `derive_decision_score`, unchanged; it's
  keyless by design.
- **Evaluation evidence assembly** — `services/evaluation/evidence.py` logic stays; only its reads
  re-point to unit-keyed tables.
- **Domain policy math** — champion/challenger rotation, promotion policy, confidence math — pure,
  reused.
- **Backtesting engine** — signal execution + walk-forward, largely reused (FK swap).
- **Migration/DB tooling** — schema init/evolution framework reused for the new DDL.

The heavy work is at the **repositories** layer (rewritten against new tables) and the **services**
that assemble unit-vs-account reads — which the convergence plan already targets.

## Cross-cutting decisions

Canonical status in [decisions.md](decisions.md); detail here.

Decided:
- **Default unit: real row** ([D7](decisions.md#d7)) — cheap under greenfield; resolves A/B toward B.
- **Strategy catalog** ([D5](decisions.md#d5)) — a strategy = primitive + knobs; variants are new
  rows; `strategy_param_sets` dropped.
- **Parameters split** ([D4](decisions.md#d4)) — strategy knobs in strategy rows; execution/risk
  settings on account/unit; P7 is a view, not a new store.
- **Decision snapshots** ([D6](decisions.md#d6)) — `decision_score` + `decision_confidence` columns
  on `rotation_decisions`; no dedicated snapshot table until adaptive learning (P10).

Still open: **none.** The account/unit settings shape (D4 tail) was decided 2026-07-03 —
per-concern typed config tables 1:1 with `trading_units` (`unit_execution_settings`,
`unit_option_settings`, `unit_rotation_settings`), goals on `trading_units`, change-audit deferred
to P7. See [decisions.md](decisions.md#d4) and the [target schema](db-schema-target.md).

## Non-goals

- No data migration (we drop old data).
- No arbitrary-logic scripting DSL — signal primitives stay code.
- No change to the human-gated live model.

## Trigger checklist (when to execute)

- [x] Execution loop closed (Plan P1, merged 2026-07-03) so runtime behavior is known-good on the
      new tables.
- [x] Convergence A/B decision landed on B (physical rework) — D2/D3/D7.
- [x] Strategy/parameter model decided — D5 + D4 (only the account/unit settings shape is a detail
      to finalize during the build).
- [x] D6 (persist decision snapshots?) resolved — score columns now, table deferred to P10.
- [ ] A pre-live window confirmed (cheapest time to change schema).
