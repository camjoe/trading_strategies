# Trading Service API — Developer Cookbook

## Purpose

Answer the question: **"Which function do I call to do X?"**

This is a task-oriented companion to [trading-package-map.md](trading-package-map.md),
which covers structural conventions.  Use this guide when writing CLI commands,
runtime jobs, or new UI backend routes that need to reach into `trading/services/`.

---

## Import pattern

All service packages expose a stable `__all__` surface through their
`__init__.py`.  Import from the package, not from the concrete submodule:

```python
# Correct — stable public surface
from trading.services.accounts import get_account, list_account_records
from trading.services.reporting import build_account_stats, build_live_benchmark_overlay

# Avoid — internal submodule (subject to change without notice)
from trading.services.accounts.core import get_account
```

---

## Account lifecycle

| Task | Function | Package |
|---|---|---|
| Look up a single account by name | `get_account(conn, name)` | `trading.services.accounts` |
| Find an account (returns `None` if missing) | `find_account(conn, name)` | `trading.services.accounts` |
| List all account rows | `list_account_records(conn)` | `trading.services.accounts` |
| List account names only | `list_account_names(conn)` | `trading.services.accounts` |
| List accounts eligible for runtime trading | `load_runtime_eligible_account_names(conn)` | `trading.services.accounts` |
| Create a standard account | `create_account(conn, config)` | `trading.services.accounts` |
| Create a managed account | `create_managed_account(conn, config)` | `trading.services.accounts` |
| Update mutable account parameters | `configure_account(conn, name, config)` | `trading.services.accounts` |
| Change the active strategy | `set_account_strategy(conn, name, strategy)` | `trading.services.accounts` |
| Set the benchmark ticker | `set_benchmark(conn, name, ticker)` | `trading.services.accounts` |
| Apply a named preset profile | `apply_account_profiles(conn, name, profiles)` | `trading.services.profiles` |

---

## Account state and equity math

| Task | Function | Package |
|---|---|---|
| Load full account state (positions, cash, costs) | `load_account_state(conn, account_id, initial_cash)` | `trading.services.accounting` |
| Load state + prices + market value + equity in one call | `build_account_stats(conn, account_row)` | `trading.services.reporting` |
| Correct equity for settlement-ticker positions | `settlement_corrected_equity(state, prices)` | `trading.services.reporting` |
| Inject settlement ticker price into a price dict | `inject_settlement_price(state, prices)` | `trading.services.reporting` |
| Extract cash component from account state | `settlement_cash(state, prices)` | `trading.services.reporting` |
| Compute market value and unrealized PnL | `compute_market_value_and_unrealized(positions, avg_cost, prices)` | `trading.services.reporting` |

---

## Snapshots and history

| Task | Function | Package |
|---|---|---|
| List equity snapshots for an account | `list_account_snapshots(conn, account_id, limit)` | `trading.services.accounts` |
| Get the single most recent snapshot | `get_latest_account_snapshot(conn, account_id)` | `trading.services.accounts` |

---

## Reporting and summarization

| Task | Function | Package |
|---|---|---|
| Full account stats tuple (state, prices, mv, unrealized, equity) | `build_account_stats(conn, row)` | `trading.services.reporting` |
| Infer account equity trend (up/down/flat) | `infer_overall_trend(conn, account_id, equity, lookback)` | `trading.services.reporting` |
| Compute account return % | `strategy_return_pct(equity, initial_cash)` | `trading.services.reporting` |
| Compute alpha vs benchmark | `alpha_pct(account_return, benchmark_return)` | `trading.services.reporting` |
| Check whether benchmark data is usable | `benchmark_available(benchmark, alpha)` | `trading.services.reporting` |
| Text summary of open positions | `positions_summary_text(positions, prices)` | `trading.services.reporting` |
| Full CLI account report (prints to stdout) | `account_report(conn, name)` | `trading.services.reporting` |
| Snapshot an account to history | `snapshot_account(conn, name)` | `trading.services.reporting` |
| Show recent snapshot history | `show_snapshots(conn, name, limit)` | `trading.services.reporting` |
| Compare strategies side-by-side | `compare_strategies(conn)` | `trading.services.reporting` |

---

## Benchmark overlay

| Task | Function | Package |
|---|---|---|
| Fetch daily close history for a ticker | `fetch_benchmark_close_history(ticker, *, start_date, end_date)` | `trading.services.reporting` |
| Compute time-aligned benchmark return overlay | `build_live_benchmark_overlay(benchmark_ticker, snapshots)` | `trading.services.reporting` |
| Inject benchmark summary fields into an account dict | `attach_live_benchmark_summary(summary, overlay)` | `trading.services.reporting` |
| Fetch benchmark price stats (current, pct change) | `benchmark_stats(ticker)` | `trading.services.reporting` |

---

## Trades and accounting

| Task | Function | Package |
|---|---|---|
| List all trades for an account | `list_account_trades(conn, account_id)` | `trading.services.accounting` |
| Record a new trade | `record_trade(conn, trade_insert)` | `trading.services.accounting` |

---

## Pricing and market data

| Task | Function | Package |
|---|---|---|
| Fetch latest prices for a list of tickers | `fetch_latest_prices(tickers)` | `trading.services.pricing` |
| Get the active market data provider | `get_provider()` | `trading.services.market_data` |
| Get the active feature data provider | `get_feature_provider()` | `trading.services.market_data` |
| Switch providers at runtime (testing/config reload) | `set_provider_by_name(name)` / `reload_provider_from_config()` | `trading.services.market_data` |

---

## Auto-trading

| Task | Function | Package |
|---|---|---|
| Run all trading-eligible accounts | `run_accounts(conn, names, mode)` | `trading.services.auto_trading` |
| Run trading for a single account | `run_for_account(conn, name, mode)` | `trading.services.auto_trading` |
| Resolve account names for a run | `resolve_account_names(conn, requested)` | `trading.services.auto_trading` |
| Resolve market inputs (prices, features) | `resolve_market_inputs(tickers)` | `trading.services.auto_trading` |
| Rotate strategy if interval has elapsed | `rotate_runtime_account_if_due(conn, name)` | `trading.services.auto_trading` |
| Reconcile open broker orders | `reconcile_open_broker_orders(conn, name, orders)` | `trading.services.auto_trading` |

---

## Sleeves (multi-strategy accounts)

| Task | Function | Package |
|---|---|---|
| Run sleeve mode for an account | `run_sleeve_mode_for_account(conn, name, mode)` | `trading.services.sleeves` |
| Generate trade intents from sleeve state | `generate_sleeve_trade_intents(conn, sleeves, prices)` | `trading.services.sleeves` |
| Apply a fill to a sleeve | `apply_sleeve_fill(conn, sleeve_id, fill)` | `trading.services.sleeves` |
| Evaluate sleeve risk gate | `evaluate_sleeve_risk_gate(conn, sleeve, config)` | `trading.services.sleeves` |
| Evaluate and apply sleeve rotation | `evaluate_and_apply_sleeve_rotation(conn, sleeve, config)` | `trading.services.sleeves` |
| Reconcile sleeve equity vs account equity | `reconcile_sleeves_vs_account_equity(conn, account_id, equity)` | `trading.services.sleeves` |
| Reconcile sleeve equity vs latest snapshot | `reconcile_sleeves_vs_latest_snapshot(conn, account_id)` | `trading.services.sleeves` |

---

## Promotion review

| Task | Function | Package |
|---|---|---|
| Fetch current promotion assessment | `fetch_current_promotion_assessment(conn, name)` | `trading.services.promotion` |
| Submit a promotion review request | `execute_promotion_review_request(conn, name, request)` | `trading.services.promotion` |
| Act on a review (approve / reject / note) | `execute_promotion_review_action(conn, name, action)` | `trading.services.promotion` |
| Fetch review history | `fetch_promotion_review_history(conn, name)` | `trading.services.promotion` |
| Render status lines for CLI output | `render_promotion_status_lines(assessment)` | `trading.services.promotion` |

---

## Strategy evaluation

| Task | Function | Package |
|---|---|---|
| Fetch strategy evaluation for an account row | `fetch_strategy_evaluation_for_account_row(conn, row)` | `trading.services.evaluation` |
| Fetch evaluation for a strategy name directly | `fetch_strategy_evaluation(conn, strategy)` | `trading.services.evaluation` |

---

## Analysis

| Task | Function | Package |
|---|---|---|
| Fetch account performance analysis | `fetch_account_analysis(conn, name)` | `trading.services.analysis` |

---

## Admin (bulk operations)

| Task | Function | Package |
|---|---|---|
| Delete accounts and all dependents | `delete_accounts(conn, names)` | `trading.services.admin` |
| Count records that would be deleted | `build_managed_account_delete_counts(conn, names)` | `trading.services.admin` |

---

## Runtime configuration

| Task | Function | Package |
|---|---|---|
| Fetch runtime throttle settings | `fetch_runtime_throttle_settings(conn)` | `trading.services.runtime_settings` |
| Update runtime throttle settings | `set_runtime_throttle_settings(conn, settings)` | `trading.services.runtime_settings` |
| Fetch promotion policy settings | `fetch_promotion_policy_settings(conn)` | `trading.services.runtime_settings` |
| Enforce trade count throttle limits | `enforce_runtime_trade_throttles(conn, account_id, count)` | `trading.services.runtime_throttle` |

---

## UI Backend boundary rule

`paper_trading_ui/backend/services/` is a **transport-only** layer.

- ✅ HTTP request → domain model conversion
- ✅ FastAPI error handling (`raise HTTPException`)
- ✅ Response payload shaping (camelCase dicts for the frontend)
- ❌ Domain calculations, business rules, or data assembly

If a calculation would be useful to a CLI command or a runtime job, it belongs
in `trading/services/` — not in the UI backend.  See
`.github/BOT_ARCHITECTURE_CONVENTIONS.md` for the full rule.

---

## Related references

- [trading-package-map.md](trading-package-map.md) — structural overview and placement rules
- [service-repository-boundary.md](service-repository-boundary.md) — how to split service vs repository responsibilities
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md` — canonical architecture rules for all bots
