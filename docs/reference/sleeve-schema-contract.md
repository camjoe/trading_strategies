# Reference Notes: Sleeve Schema Contract (Increment 0)

Type: notes
Status: Draft
Created: 2026-05-03
Last Reviewed: 2026-07-02
Purpose: Define the concrete sleeve table and index contract for IBKR paper autonomy before coding migrations and repositories.
Related: [ADR: Sleeve Virtualization](../adr/003-sleeve-virtualization-architecture.md), [Accounts Schema Usage](accounts-schema-usage.md), [DB Migration System](db-migration-system.md)

> **Pre-P3 schema.** This describes the *current* sleeve tables, which the greenfield DB rewrite
> (Plan P3) replaces with the trading-unit schema in
> [db-schema-target.md](../db-schema-target.md) (`strategy_sleeves` → `trading_units`,
> `sleeve_*` tables folded into unit-keyed `orders`/`order_fills`/`positions`/`ledger`). Treat this
> doc as historical once P3 lands — do not use it as a design target.

## Purpose

Define the concrete sleeve table and index contract for the IBKR paper autonomy program before coding migrations and repositories.

## Migration Approach

1. Add new table and index DDL to `src/infrastructure/database/schema.py`.
2. Keep schema changes additive-only.
3. Reuse existing init flow in `src/infrastructure/database/init.py`.
4. Use `ColumnMigration` tuples in `src/infrastructure/database/migrations.py` only for future additive column evolutions on sleeve tables.
5. Do not introduce a separate migration system.

## Table Contracts

## `strategy_sleeves`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `account_id INTEGER NOT NULL` FK `accounts(id)`
3. `name TEXT NOT NULL`
4. `status TEXT NOT NULL` CHECK in `('active','paused','retired')`
5. `base_ccy TEXT NOT NULL DEFAULT 'USD'`
6. `start_equity REAL NOT NULL`
7. `current_cash REAL NOT NULL`
8. `current_equity REAL NOT NULL`
9. `created_at TEXT NOT NULL`
10. `updated_at TEXT NOT NULL`

Constraints and indexes:

1. `UNIQUE(account_id, name)`
2. Index: `(account_id, status)`

---

## `strategy_param_sets`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `strategy_name TEXT NOT NULL`
3. `version TEXT NOT NULL`
4. `params_json TEXT NOT NULL`
5. `config_version TEXT`
6. `is_active INTEGER NOT NULL DEFAULT 0`
7. `created_at TEXT NOT NULL`
8. `updated_at TEXT NOT NULL`
9. `activated_at TEXT`
10. `deactivated_at TEXT`
11. `notes TEXT`

Constraints and indexes:

1. `UNIQUE(strategy_name, version)`
2. Index: `(strategy_name, is_active)`

---

## `sleeve_strategy_assignments`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `sleeve_id INTEGER NOT NULL` FK `strategy_sleeves(id)`
3. `strategy_name TEXT NOT NULL`
4. `param_set_id INTEGER` FK `strategy_param_sets(id)`
5. `effective_from TEXT NOT NULL`
6. `effective_to TEXT`
7. `is_incumbent INTEGER NOT NULL DEFAULT 1`
8. `created_at TEXT NOT NULL`
9. `updated_at TEXT NOT NULL`

Constraints and indexes:

1. Partial unique index for one active incumbent per sleeve:
   - `UNIQUE(sleeve_id) WHERE is_incumbent = 1 AND effective_to IS NULL`
2. Index: `(sleeve_id, effective_from DESC)`
3. Index: `(strategy_name, effective_from DESC)`

---

## `rotation_decisions`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `sleeve_id INTEGER NOT NULL` FK `strategy_sleeves(id)`
4. `decision_time TEXT NOT NULL`
5. `incumbent_strategy TEXT`
6. `challenger_strategy TEXT`
7. `selected_strategy TEXT`
8. `rotation_action TEXT NOT NULL` CHECK in `('hold','rotate')`
9. `cooldown_active INTEGER NOT NULL DEFAULT 0`
10. `score_components_json TEXT NOT NULL`
11. `gate_results_json TEXT NOT NULL`
12. `decision_reason TEXT`
13. `config_version TEXT`
14. `param_set_id INTEGER` FK `strategy_param_sets(id)`
15. `created_at TEXT NOT NULL`

Constraints and indexes:

1. Index: `(sleeve_id, decision_time DESC)`
2. Index: `(rotation_action, decision_time DESC)`

---

## `sleeve_orders`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `account_id INTEGER NOT NULL` FK `accounts(id)`
3. `sleeve_id INTEGER NOT NULL` FK `strategy_sleeves(id)`
4. `strategy_name TEXT NOT NULL`
5. `param_set_id INTEGER` FK `strategy_param_sets(id)`
6. `rotation_decision_id INTEGER` FK `rotation_decisions(id)`
7. `broker_order_id TEXT`
8. `symbol TEXT NOT NULL`
9. `side TEXT NOT NULL` CHECK in `('buy','sell')`
10. `qty REAL NOT NULL`
11. `order_type TEXT NOT NULL DEFAULT 'market'`
12. `time_in_force TEXT NOT NULL DEFAULT 'day'`
13. `requested_price REAL NOT NULL`
14. `status TEXT NOT NULL`
15. `config_version TEXT`
16. `submitted_at TEXT NOT NULL`
17. `updated_at TEXT NOT NULL`

Constraints and indexes:

1. Partial unique index for broker idempotency:
   - `UNIQUE(account_id, broker_order_id) WHERE broker_order_id IS NOT NULL`
2. Index: `(sleeve_id, submitted_at DESC)`
3. Index: `(account_id, status, submitted_at DESC)`

---

## `sleeve_fills`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `sleeve_order_id INTEGER NOT NULL` FK `sleeve_orders(id)`
3. `sleeve_id INTEGER NOT NULL` FK `strategy_sleeves(id)`
4. `broker_fill_id TEXT`
5. `exec_id TEXT`
6. `symbol TEXT NOT NULL`
7. `filled_qty REAL NOT NULL`
8. `fill_price REAL NOT NULL`
9. `commission REAL NOT NULL DEFAULT 0`
10. `fill_time TEXT NOT NULL`

Constraints and indexes:

1. Partial unique index for reconciliation idempotency:
   - `UNIQUE(sleeve_order_id, exec_id) WHERE exec_id IS NOT NULL`
2. Index: `(sleeve_id, fill_time DESC)`
3. Index: `(sleeve_order_id, fill_time DESC)`

---

## `sleeve_positions`

Columns:

1. `sleeve_id INTEGER NOT NULL` FK `strategy_sleeves(id)`
2. `symbol TEXT NOT NULL`
3. `qty REAL NOT NULL`
4. `avg_cost REAL NOT NULL`
5. `market_value REAL NOT NULL`
6. `unrealized_pnl REAL NOT NULL`
7. `updated_at TEXT NOT NULL`

Constraints and indexes:

1. `PRIMARY KEY (sleeve_id, symbol)`
2. Index: `(symbol, updated_at DESC)`

---

## `sleeve_ledger`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `sleeve_id INTEGER NOT NULL` FK `strategy_sleeves(id)`
3. `entry_type TEXT NOT NULL` CHECK in `('cash_movement','realized_pnl','fee','financing','transfer')`
4. `amount REAL NOT NULL`
5. `reference_type TEXT`
6. `reference_id TEXT`
7. `entry_time TEXT NOT NULL`
8. `created_at TEXT NOT NULL`

Constraints and indexes:

1. Index: `(sleeve_id, entry_time DESC)`
2. Index: `(reference_type, reference_id)`

---

## `portfolio_risk_snapshots`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `account_id INTEGER NOT NULL` FK `accounts(id)`
3. `snapshot_time TEXT NOT NULL`
4. `gross_exposure REAL NOT NULL`
5. `net_exposure REAL NOT NULL`
6. `max_symbol_concentration_pct REAL NOT NULL`
7. `max_sector_concentration_pct REAL NOT NULL`
8. `drawdown_pct REAL`
9. `leverage_proxy REAL`
10. `daily_loss_pct REAL`
11. `kill_switch_triggered INTEGER NOT NULL DEFAULT 0`
12. `risk_payload_json TEXT NOT NULL`

Constraints and indexes:

1. `UNIQUE(account_id, snapshot_time)`
2. Index: `(account_id, snapshot_time DESC)`

---

## `daily_metrics`

Columns:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `account_id INTEGER NOT NULL` FK `accounts(id)`
3. `sleeve_id INTEGER` FK `strategy_sleeves(id)` (NULL indicates portfolio aggregate row)
4. `metric_date TEXT NOT NULL`
5. `return_pct REAL`
6. `drawdown_pct REAL`
7. `turnover_pct REAL`
8. `slippage_bps REAL`
9. `hit_rate REAL`
10. `expectancy REAL`
11. `risk_adjusted_score REAL`
12. `trade_count INTEGER`
13. `fees_total REAL`
14. `created_at TEXT NOT NULL`
15. `updated_at TEXT NOT NULL`

Constraints and indexes:

1. `UNIQUE(account_id, sleeve_id, metric_date)`
2. Index: `(account_id, metric_date DESC)`
3. Index: `(sleeve_id, metric_date DESC)`

## Reconciliation and Compatibility Notes

1. Broker account remains the source of execution truth.
2. Sleeve tables are internal attribution and decision layers.
3. Account-level `broker_orders`, `order_fills`, and `trades` remain in place during migration for backward compatibility and parity testing.
4. Consolidation/removal of old overlapping paths happens only after sleeve-mode acceptance tests are green.

## Decisions Locked for Increment 1 (Simplicity First)

1. `strategy_name` remains a validated text identifier (no strategy catalog FK table yet).
2. `rotation_decisions` is sleeve-only (`sleeve_id NOT NULL`).
3. `sleeve_orders` does not include `target_qty` or `target_notional` in Increment 1.
4. `config_version` remains a text field on event tables in Increment 1 (no normalized config-version table yet).
