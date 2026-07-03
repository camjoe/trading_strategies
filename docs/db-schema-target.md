# Database Schema — Target (WIP)

Type: spec
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-03
Purpose: The proposed final database schema on its own — the clean end-state, without the old schema
or change/consolidation framing. Rationale, old→new mapping, data-loss assessment, and open decisions
live in the [DB Schema Rewrite Spec](db-schema-rewrite-spec.md).
Related: [DB Schema Rewrite Spec](db-schema-rewrite-spec.md), [Overview](overview.md),
[Developer Notes](developer-notes.md)

> All schema-gating decisions are resolved (D4 settings shape settled 2026-07-03). This is the
> build target for P3 Phase A.

## Conventions, constraints & invariants

**Storage conventions**
- SQLite with `PRAGMA foreign_keys = ON`; every `*_id` reference is a real FK.
- Timestamps are ISO-8601 UTC `TEXT`; `created_at`/`updated_at`/event times are `NOT NULL` (optional
  only where genuinely absent — `effective_to`, `closed_at`, `broker_order_id` until acked).
- Money/quantity are `REAL`, consistent with the existing codebase. **Robustness flag (decide before
  live):** consider integer minor-units to avoid float drift.
- Boolean flags are `INTEGER CHECK (col IN (0,1))`.
- Status/enum columns carry `CHECK (col IN (...))` against the vocabularies below.
- `ON DELETE`: derived/operational children of an account/unit CASCADE (`positions`, `orders`,
  `order_fills`, `ledger`, `equity_snapshots`, `daily_metrics`, `trading_units`); **audit/history**
  tables RESTRICT (`promotion_reviews`+events, `rotation_decisions`, `risk_snapshots`,
  `risk_decisions`, backtests) — never silently drop history.

**Status vocabularies** (CHECK-constrained)
- `trading_units.status`: `active` | `paused` | `closed`
- `strategies.status`: `draft` | `frozen` | `retired`
- `orders.status`: `submitted` | `partially_filled` | `filled` | `rejected` | `cancelled`
- `side`: `buy` | `sell` · `orders.order_type`: `market` | `limit` · `time_in_force`: `day` | `gtc`
- `rotation_decisions.rotation_action`: `hold` | `rotate`
- `ledger.entry_type`: `trade` | `fee` | `deposit` | `withdrawal` | `adjustment`
- `risk_decisions.action`: `allow` | `block` | `rescale`
- `promotion_reviews.review_state`/`assessment_stage`/`assessment_status`: today's promotion vocab
  (preserved).

**Invariants** (enforced in repositories/services, not only DB where noted)
1. **One default unit per account** — `UNIQUE (account_id) WHERE is_default = 1`. A plain account has
   exactly that one unit.
2. **One open assignment per unit** — `UNIQUE (unit_id) WHERE effective_to IS NULL` (the incumbent).
3. **Equity reconciles** — Σ unit equity == account equity == broker/custody truth (kill-switch guard).
4. **Order ↔ unit ↔ account integrity** — `orders.unit_id` must belong to `orders.account_id`
   (service-enforced; SQLite can't express a two-column composite FK to this shape cheaply).
5. **Strategy immutability** — a `strategies` row is frozen (knobs immutable) once it has backtest
   evidence or is live; tuning creates a new row. Enforced in the strategies repository/service.
6. **Live gate** — `live_trading_enabled` is human-set only; never by code, migration, seed, or test.

**Indexes** (beyond PKs / the UNIQUEs above)
- `trading_units (account_id, status)`
- `unit_strategy_assignments (unit_id, effective_from)`, `(strategy_id, effective_from)`
- `rotation_decisions (unit_id, decision_time)`, `(rotation_action, decision_time)`
- `orders (account_id, status, submitted_at)`, `(unit_id, submitted_at)`
- `order_fills (order_id)`; UNIQUE `(order_id, exec_id)`
- `positions (symbol, updated_at)` (PK is `(unit_id, symbol)`)
- `ledger (unit_id, entry_time)`, `(reference_type, reference_id)`
- `equity_snapshots (unit_id, snapshot_time)`; UNIQUE `(unit_id, snapshot_time)`
- `daily_metrics` UNIQUE `(unit_id, metric_date)`
- `risk_snapshots (account_id, snapshot_time)`; `risk_decisions (account_id, decision_time)`, `(unit_id, decision_time)`
- `promotion_reviews (review_state, updated_at)`; UNIQUE open review `(account_id, strategy_id) WHERE closed_at IS NULL`; `promotion_review_events (review_id, event_seq)` UNIQUE
- backtests: `backtest_runs (account_id, strategy_id)`, `backtest_trades (run_id)`,
  `backtest_equity_snapshots (run_id)`, `walk_forward_groups (grouping_key)` UNIQUE,
  `walk_forward_group_runs (group_id, window_index)` UNIQUE

## Custody & units

### `accounts` — custody/broker root
- `id` INTEGER PK
- `name` TEXT UNIQUE NOT NULL
- `descriptive_name` TEXT
- `base_ccy` TEXT NOT NULL DEFAULT 'USD'
- `initial_cash` REAL NOT NULL
- `benchmark_ticker` TEXT NOT NULL DEFAULT 'SPY'
- `broker_type` TEXT NOT NULL DEFAULT 'paper'
- `broker_host` TEXT · `broker_port` INTEGER · `broker_client_id` INTEGER
- `live_trading_enabled` INTEGER NOT NULL DEFAULT 0  *(hard safety gate; human-set only)*
- `created_at` TEXT · `updated_at` TEXT

### `trading_units` — the strategy-execution primitive
- `id` INTEGER PK
- `account_id` INTEGER NOT NULL → accounts.id
- `name` TEXT NOT NULL
- `status` TEXT NOT NULL DEFAULT 'active'  *(active | paused | closed)*
- `is_default` INTEGER NOT NULL DEFAULT 0
- `start_equity` REAL NOT NULL · `current_cash` REAL NOT NULL · `current_equity` REAL NOT NULL
- `trade_universes` TEXT (json)
- `goal_min_return_pct` REAL · `goal_max_return_pct` REAL · `goal_period` TEXT  *(unit mandate
  metadata — reporting targets, not execution settings)*
- `created_at` TEXT NOT NULL · `updated_at` TEXT NOT NULL
- UNIQUE (account_id, name)
- UNIQUE (account_id) WHERE is_default = 1  *(exactly one default unit per account — invariant 1)*

## Strategy catalog & parameters (data-driven)

### `strategies` — data-defined catalog; a strategy = a code primitive + its knobs (D5)
- `id` INTEGER PK
- `strategy_key` TEXT UNIQUE NOT NULL  *(the strategy's name)*
- `primitive` TEXT NOT NULL  *(name of the code signal-primitive it binds to)*
- `params_json` TEXT NOT NULL  *(the knobs — e.g. `{"fast_window":5,"slow_window":15}`)*
- `style` TEXT NOT NULL  *(trend / mean_reversion / neutral / alternative)*
- `required_features` TEXT (json)
- `description` TEXT
- `status` TEXT NOT NULL DEFAULT 'draft'  *(draft = editable; frozen once it has evidence / is live)*
- `enabled` INTEGER NOT NULL DEFAULT 1
- `created_at` TEXT · `updated_at` TEXT
- **Variants/tuning = new rows** (same primitive, different knobs). No separate param-set table;
  frozen-once-used gives history automatically (D5).

*(`strategy_param_sets` is removed — its purpose is folded into `strategies` rows.)*

### Unit settings — per-concern typed config tables (D4, decided 2026-07-03)

One row per unit per concern, keyed 1:1 to `trading_units` (`unit_id` INTEGER PK →
trading_units.id, ON DELETE CASCADE). **Missing row → code defaults.** Change-audit deferred to P7
(settings change only via seed/bootstrap CLI until then); each table carries
`created_at`/`updated_at` NOT NULL. The **unified parameter source (P7)** is a service/CLI view
over strategy rows + these settings + a few global settings, not a new store.

#### `unit_execution_settings`
- `unit_id` INTEGER PK → trading_units.id
- `learning_enabled` INTEGER NOT NULL DEFAULT 0  *(selection-inert since P1; retained for P10)*
- `risk_policy` TEXT NOT NULL DEFAULT 'none'  *(none | fixed_stop | take_profit | stop_and_target)*
- `stop_loss_pct` REAL · `take_profit_pct` REAL · `profit_take_pct` REAL · `max_loss_pct` REAL
- `trade_size_pct` REAL · `max_position_pct` REAL
- `max_trades_per_run` INTEGER  *(per-run cap; NULL = runtime/CLI default)*
- `instrument_mode` TEXT NOT NULL DEFAULT 'equity'  *(equity | leaps)*
- `created_at` TEXT NOT NULL · `updated_at` TEXT NOT NULL

#### `unit_option_settings` *(row exists only for option-capable units)*
- `unit_id` INTEGER PK → trading_units.id
- `option_strike_offset_pct` REAL · `option_min_dte` INTEGER · `option_max_dte` INTEGER
- `option_type` TEXT  *(call | put)*
- `target_delta_min` REAL · `target_delta_max` REAL
- `max_premium_per_trade` REAL · `max_contracts_per_trade` INTEGER
- `iv_rank_min` REAL · `iv_rank_max` REAL
- `roll_dte_threshold` INTEGER
- `created_at` TEXT NOT NULL · `updated_at` TEXT NOT NULL

#### `unit_rotation_settings` *(settings only — rotation **state** is the open
`unit_strategy_assignments` row + `rotation_decisions` history, not columns here)*
- `unit_id` INTEGER PK → trading_units.id
- `rotation_enabled` INTEGER NOT NULL DEFAULT 0
- `rotation_mode` TEXT · `rotation_optimality_mode` TEXT
- `rotation_interval_days` INTEGER · `rotation_interval_minutes` INTEGER
- `rotation_lookback_days` INTEGER
- `rotation_schedule` TEXT (json)  *(ordered candidate strategy keys)*
- `regime_strategy_risk_on_id` · `regime_strategy_neutral_id` · `regime_strategy_risk_off_id`
  INTEGER → strategies.id
- `overlay_mode` TEXT · `overlay_min_tickers` INTEGER · `overlay_confidence_threshold` REAL
- `overlay_watchlist` TEXT (json)
- `created_at` TEXT NOT NULL · `updated_at` TEXT NOT NULL

### `feature_providers` — pluggable provider catalog
- `id` INTEGER PK · `provider_key` TEXT UNIQUE NOT NULL
- `enabled` INTEGER NOT NULL DEFAULT 0 · `config_json` TEXT
- `created_at` TEXT · `updated_at` TEXT

## Assignment & rotation (one model)

### `unit_strategy_assignments`
- `id` INTEGER PK
- `unit_id` INTEGER NOT NULL → trading_units.id
- `strategy_id` INTEGER NOT NULL → strategies.id  *(the strategy row carries its own knobs — D5)*
- `effective_from` TEXT NOT NULL · `effective_to` TEXT  *(NULL = open/incumbent)*
- `is_incumbent` INTEGER NOT NULL DEFAULT 1 CHECK (is_incumbent IN (0,1))
- `created_at` TEXT NOT NULL · `updated_at` TEXT NOT NULL
- UNIQUE (unit_id) WHERE effective_to IS NULL  *(one open assignment per unit — invariant 2)*

### `rotation_decisions` — unifies sleeve champion/challenger + account episode
- `id` INTEGER PK
- `unit_id` INTEGER NOT NULL → trading_units.id
- `decision_time` TEXT NOT NULL
- `incumbent_strategy_id` · `challenger_strategy_id` · `selected_strategy_id` INTEGER
- `rotation_action` TEXT NOT NULL · `cooldown_active` INTEGER NOT NULL DEFAULT 0
- `decision_score` REAL · `decision_confidence` REAL  *(first-class score history — D6)*
- `score_components_json` TEXT · `gate_results_json` TEXT · `decision_reason` TEXT
- `config_version` TEXT
- `window_start` TEXT · `window_end` TEXT · `realized_pnl_delta` REAL  *(folds episode fields)*
- `created_at` TEXT

## Execution & accounting (one model, keyed by unit)

### `orders` — unifies broker_orders + sleeve_orders
- `id` INTEGER PK
- `unit_id` INTEGER NOT NULL → trading_units.id · `account_id` INTEGER NOT NULL → accounts.id
- `strategy_id` INTEGER · `rotation_decision_id` INTEGER
- `broker_order_id` TEXT  *(custody linkage; nullable until acked)*
- `symbol` TEXT · `side` TEXT · `qty` REAL
- `order_type` TEXT NOT NULL DEFAULT 'market' · `time_in_force` TEXT NOT NULL DEFAULT 'day'
- `requested_price` REAL · `status` TEXT NOT NULL
- `filled_qty` REAL NOT NULL DEFAULT 0 · `avg_fill_price` REAL · `commission` REAL NOT NULL DEFAULT 0
- `submitted_at` TEXT · `updated_at` TEXT
- UNIQUE (account_id, broker_order_id)

### `order_fills` — unifies order_fills + sleeve_fills
- `id` INTEGER PK
- `order_id` INTEGER NOT NULL → orders.id
- `broker_fill_id` TEXT · `exec_id` TEXT
- `filled_qty` REAL · `fill_price` REAL · `commission` REAL NOT NULL DEFAULT 0 · `fill_time` TEXT
- UNIQUE (order_id, exec_id)

### `positions` — replaces sleeve_positions
- `unit_id` INTEGER NOT NULL → trading_units.id
- `symbol` TEXT NOT NULL
- `qty` REAL · `avg_cost` REAL · `market_value` REAL · `unrealized_pnl` REAL · `updated_at` TEXT
- PK (unit_id, symbol)

### `ledger` — unifies sleeve_ledger + account trades
- `id` INTEGER PK
- `unit_id` INTEGER NOT NULL → trading_units.id
- `entry_type` TEXT NOT NULL · `amount` REAL NOT NULL
- `reference_type` TEXT · `reference_id` TEXT
- `entry_time` TEXT NOT NULL · `created_at` TEXT

### `equity_snapshots` — per unit (account view = roll-up)
- `id` INTEGER PK
- `unit_id` INTEGER NOT NULL → trading_units.id
- `snapshot_time` TEXT NOT NULL
- `cash` REAL · `market_value` REAL · `equity` REAL · `realized_pnl` REAL · `unrealized_pnl` REAL

## Evaluation, risk, promotion

### `daily_metrics` — per unit
- `id` INTEGER PK · `unit_id` INTEGER NOT NULL → trading_units.id
- `metric_date` TEXT NOT NULL
- `return_pct` · `drawdown_pct` · `turnover_pct` · `slippage_bps` · `hit_rate` · `expectancy`
  · `risk_adjusted_score` REAL · `trade_count` INTEGER · `fees_total` REAL
- `created_at` TEXT · `updated_at` TEXT
- UNIQUE (unit_id, metric_date)

### `risk_snapshots` / `risk_decisions`
- `risk_snapshots`: `id`, `account_id`, `snapshot_time`, `gross_exposure`, `net_exposure`,
  `max_symbol_concentration_pct`, `max_sector_concentration_pct`, `drawdown_pct`, `leverage_proxy`,
  `daily_loss_pct`, `kill_switch_triggered`, `risk_payload_json`.
- `risk_decisions`: `id`, `account_id`, `unit_id`, `decision_time`, `symbol`, `side`, `action`,
  `reason_code`, `requested_qty`, `approved_qty`, `requested_notional`, `approved_notional`,
  `risk_payload_json`, `created_at`.

### `promotion_reviews` / `promotion_review_events` — human-gated audit (retained)
- `promotion_reviews`: `id`, `account_id`, `account_name_snapshot`, `unit_id`, `strategy_id`,
  `review_state`, `assessment_stage`, `assessment_status`, `ready_for_live`, `overall_confidence`,
  `live_trading_enabled_snapshot`, `promotion_assessment_version`, `evaluation_artifact_version`,
  `frozen_assessment_payload`, `frozen_evaluation_payload`, `requested_by`, `reviewed_by`,
  `operator_summary_note`, `created_at`, `updated_at`, `closed_at`.
- `promotion_review_events`: `id`, `review_id`, `event_seq`, `event_type`, `actor_type`,
  `actor_name`, `from_review_state`, `to_review_state`, `note`, `event_payload`, `created_at`.
- Decision snapshots: score columns live on `rotation_decisions` (D6); a dedicated
  `decision_snapshots` table is deferred to adaptive learning (P10).

## Backtesting (structurally stable; strategy_id FK)

- `backtest_runs`: `id`, `account_id`, `strategy_id`, `run_name`, `start_date`, `end_date`,
  `created_at`, `slippage_bps`, `fee_per_trade`, `tickers_file`, `notes`, `warnings`.
- `backtest_trades`: `id`, `run_id`, `trade_time`, `ticker`, `side`, `qty`, `price`, `fee`,
  `slippage_bps`, `note`.
- `backtest_equity_snapshots`: `id`, `run_id`, `snapshot_time`, `cash`, `market_value`, `equity`,
  `realized_pnl`, `unrealized_pnl`.
- `walk_forward_groups`: `id`, `grouping_key`, `account_id`, `strategy_id`, `run_name_prefix`,
  `start_date`, `end_date`, `test_months`, `step_months`, `window_count`, `average_return_pct`,
  `median_return_pct`, `best_return_pct`, `worst_return_pct`, `created_at`.
- `walk_forward_group_runs`: `id`, `group_id`, `run_id`, `window_index`, `window_start`,
  `window_end`, `total_return_pct`.
