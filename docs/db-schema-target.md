# Database Schema — Target (WIP)

Type: spec
Status: WIP
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: The proposed final database schema on its own — the clean end-state, without the old schema
or change/consolidation framing. Rationale, old→new mapping, data-loss assessment, and open decisions
live in the [DB Schema Rewrite Spec](db-schema-rewrite-spec.md).
Related: [DB Schema Rewrite Spec](db-schema-rewrite-spec.md), [Overview](overview.md),
[Developer Notes](developer-notes.md)

> **WIP.** This is the *goal* view. It will change as the spec's open decisions are resolved (default
> unit real-vs-virtual, `parameters` model shape, persisted decision snapshots, strategy catalog
> granularity). Items marked (TBD) are not yet settled.

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
- `status` TEXT NOT NULL
- `is_default` INTEGER NOT NULL DEFAULT 0  *(a plain account has one default unit)*
- `start_equity` REAL · `current_cash` REAL · `current_equity` REAL
- `trade_universes` TEXT (json)
- `created_at` TEXT · `updated_at` TEXT
- UNIQUE (account_id, name)

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

### Account / unit settings (D4)
Execution/risk/rotation settings (risk policy, stop-loss, position sizing, max-trades-per-run,
rotation cooldown, instrument/option config) live on `accounts` and/or `trading_units` — **not** in a
god-table and **not** strategy knobs. Exact shape (typed columns vs a small typed config table per
concern) is the open tail of [D4](decisions.md#d4). The **unified parameter source (P7)** is a
service/CLI view over strategy rows + account/unit settings + a few global settings, not a new store.

### `feature_providers` — pluggable provider catalog
- `id` INTEGER PK · `provider_key` TEXT UNIQUE NOT NULL
- `enabled` INTEGER NOT NULL DEFAULT 0 · `config_json` TEXT
- `created_at` TEXT · `updated_at` TEXT

## Assignment & rotation (one model)

### `unit_strategy_assignments`
- `id` INTEGER PK
- `unit_id` INTEGER NOT NULL → trading_units.id
- `strategy_id` INTEGER NOT NULL → strategies.id  *(the strategy row carries its own knobs — D5)*
- `effective_from` TEXT NOT NULL · `effective_to` TEXT
- `is_incumbent` INTEGER NOT NULL DEFAULT 1
- `created_at` TEXT · `updated_at` TEXT
- UNIQUE active incumbent per unit

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
- (TBD) optional `decision_snapshots` table if we choose to persist decision scores at rotation/
  promotion time (aids adaptive learning).

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
