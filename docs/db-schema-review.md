# DB Schema Review — table-by-table walkthrough

Type: notes
Status: Draft
Created: 2026-07-17
Last Reviewed: 2026-07-21
Purpose: Track the table-by-table schema review — findings, decisions, and deferred cleanup — for the trading database.
Related: [Database Schema](reference/db-schema.md), [Walk-Forward Optimization Plan](reference/walk-forward-optimization-plan.md)

Working notes for the `features/db-final-overview` schema review (started 2026-07-17).
Findings are logged by disposition; nothing here is a change commitment until decided.

## Findings

### Future warnings (no action now — revisit if circumstances change)

- **`accounts.base_ccy`** — unread/unwritten by application code; all rows `'USD'`.
  Kept deliberately: it is declarative metadata — the one place the denomination of
  every monetary REAL in the account subtree is stated. Becomes load-bearing the day
  anything non-USD appears. Optional future hardening: IBKR adapter asserts the broker
  account's currency matches `base_ccy` at connect time. Do not drop without deciding
  the system is USD-only forever.

### Under discussion

- **`book_rotation_settings` dead columns (11)** — reviewed by the problem each group
  was solving (2026-07-17):
  - *Group 1 — Cadence* (`rotation_mode`, `rotation_optimality_mode`,
    `rotation_interval_days`, `rotation_interval_minutes`): problem ("when to
    reconsider strategy") is solved better by the live design — continuous
    evaluation + `cooldown_days` + `min_trades_in_window` (ADR 014). No capability
    lost by removal.
    **Decision (Cameron, 2026-07-17): drop** — no reason to keep; include in the
    next cleanup migration.
  - *Group 2 — Regime mapping* (`regime_strategy_{risk_on,neutral,risk_off}_id`):
    problem ("adapt strategy to market regime") is **open** — see the score-stub
    finding below. These hard-mapping columns are not the revival path (ADR 014
    chose the score-based shape); the fix is code, not schema.
    **Decision: pending** — tied to the score-stub direction below.
  - *Group 3 — Overlay* (`overlay_mode`, `overlay_min_tickers`,
    `overlay_confidence_threshold`, `overlay_watchlist`): the universe-scoping half
    of the problem is solved by `books.trade_universes` + `book_universe_history`;
    confidence-gating was cut deliberately.
    **Decision: pending.**

- **Rotation score model is 4/5 stubbed** — `RotationStrategyMetrics` is built in
  exactly one place (`src/trading/services/books/rotation_metrics.py`) with
  `stability=0.0`, `drawdown_penalty=0.0`, `cost_penalty=0.0`, `regime_fit=0.0`
  hardcoded. Four of the five score weights in `book_rotation_settings` multiply
  constant zeros; the rotation score is effectively single-factor (risk-adjusted
  return). The schema is ahead of the code — hooking these up is feature work
  (regime data is available via the `policy_regime` feature fetcher). Decide:
  compute the missing metrics, or simplify the weight columns to match reality.
- **`daily_metrics` has no writer** — three read paths (book daily report, analysis
  performance, IBKR paper monitor) but `DailyMetricsRepository.upsert` is never called
  anywhere. Table is always empty in production; readers silently render None.
  Options: build the writer job, drop table + readers, or leave and decide later.

### Planned evolutions (future work, not drift)

- **`walk_forward_groups` / `walk_forward_group_runs` / `backtest_runs`** — the
  walk-forward optimization plan (`docs/reference/walk-forward-optimization-plan.md`,
  reviewed together 2026-07-17) will evolve these additively: experiment metadata +
  lifecycle status on groups, train-window boundaries + frozen selection on windows,
  a new trials table, and `run_purpose` + snapshot provenance on backtest_runs.
  Current shapes are correct for today's rolling-window capability; do not "clean up"
  these tables in ways that conflict with that plan. Not scheduled — future decision.

### Execution/accounting quartet (orders, order_fills, ledger, positions) — reviewed 2026-07-17

Design verdict: sound. `order_fills` is the event log; `orders` rollups, `positions`,
`ledger`, and `books.current_cash/current_equity` are derived projections — deliberate
and correctly documented in `services/execution/submission.py`. Idempotent reconciliation
via `UNIQUE(order_id, exec_id)`; broker dedupe via partial unique
`(account_id, broker_order_id)`. Rejected alternatives: double-entry ledger,
event-sourced orders, ledger-as-sole-cash-truth, compute-positions-on-read
(all disproportionate for this system).

Findings:

1. **Fill accounting was not atomic** — `apply_book_fill` spanned ~5 separately
   committed writes (fill → position → ledger trade → ledger fee → book balances)
   because every repository method self-committed. Crash mid-sequence left
   inconsistent projections, and exec_id dedup would then skip the fill on re-run,
   never applying its cash effect. **DONE (2026-07-21, its own commit):** added
   `trading/repositories/unit_of_work.py` — a re-entrant `unit_of_work(conn)`
   scope in which the seven fill-path repository writes call `maybe_commit`
   (no-op inside the scope) so the whole sequence commits once or rolls back
   entirely. `apply_book_fill` and the three callers (submission, reconciliation,
   manual accounting) wrap their per-order sequences. Guarded by
   `tests/src/trading/repositories/test_unit_of_work.py` and
   `tests/src/trading/services/execution/test_fill_atomicity.py`. Placed in the
   repository layer, not `infrastructure/database/`, to satisfy the
   "services → no direct database imports" boundary.
2. **No status_reason on orders** — broker rejection/cancellation reasons were lost
   (gate blocks are captured in risk_decisions, broker reasons were not).
   **DONE (revision 0010, 2026-07-21):** nullable `status_reason TEXT` added; wired
   end to end `BrokerOrder.status_reason` → `OrderRepository.insert`/`update_status`
   (COALESCEd so a later poll cannot erase a recorded reason). Follow-up: the IB
   adapters do not populate `BrokerOrder.status_reason` yet — a bounded change under
   the Live Trading Safety Guard.
3. **`order_fills.broker_fill_id` was duplicative** — every write site set it to the
   parent order's `broker_order_id`, never a per-fill id; `exec_id` carries per-fill
   identity + dedupe. **DONE (revision 0010, 2026-07-21):** column dropped, parameter
   removed from `insert_fill` and all three call sites.
4. Documented assumptions (fine, but schema-level): `positions` cannot represent a
   short (qty ≤ 0 deletes the row); `market_value`/`unrealized_pnl` are fill-marked
   until the NAV pass re-marks them.

### Noted, low priority

- **Five redundant indexes** — `idx_equity_snapshots_book_time`,
  `idx_daily_metrics_book_date`, `idx_risk_snapshots_account_time`,
  `idx_promotion_review_events_review_seq`, `idx_walk_forward_group_runs_group_window`
  each duplicate their table's UNIQUE auto-index (SQLite scans indexes in both
  directions, so the DESC copies add nothing). Cost: extra write work on high-volume
  tables. Could ride along in any future rebuild of those tables.

## Walkthrough checklist

Reviewed together = discussed one-by-one in session, not just audited by tooling.

| # | Table | Audit signal | Reviewed together |
|---|---|---|---|
| 1 | accounts | `base_ccy` finding above; rest clean | in progress |
| 2 | books | wide by design (0004/0005); all columns used | |
| 3 | book_rotation_settings | 11 dead columns (see above) | in progress |
| 4 | book_strategy_assignments | clean | |
| 5 | book_universe_history | clean (new in 0008) | |
| 6 | strategies | clean | |
| 7 | feature_providers | clean | |
| 8 | global_settings | clean | |
| 9 | orders | see quartet findings (atomicity, status_reason) | reviewed 2026-07-17 |
| 10 | order_fills | see quartet findings (broker_fill_id) | reviewed 2026-07-17 |
| 11 | positions | see quartet findings (long-only assumption) | reviewed 2026-07-17 |
| 12 | ledger | see quartet findings (sound as-is) | reviewed 2026-07-17 |
| 13 | equity_snapshots | clean | |
| 14 | daily_metrics | no writer (see above) | |
| 15 | risk_snapshots | clean | |
| 16 | risk_decisions | clean (qty widened to REAL in 0009) | |
| 17 | rotation_decisions | clean; low-ref columns are write-once telemetry | |
| 18 | backtest_runs | clean | |
| 19 | backtest_trades | clean | |
| 20 | backtest_equity_snapshots | clean | |
| 21 | walk_forward_groups | clean; planned evolution — see walk-forward-optimization-plan.md | reviewed 2026-07-17 |
| 22 | walk_forward_group_runs | clean; planned evolution — see walk-forward-optimization-plan.md | reviewed 2026-07-17 |
| 23 | promotion_reviews | clean; snapshot/frozen columns deliberate | |
| 24 | promotion_review_events | clean | |
