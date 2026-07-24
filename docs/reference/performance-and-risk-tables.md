# Performance and Risk Tables

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-07-21
Purpose: Provide the current table contract for performance snapshots, daily metrics, risk snapshots, risk decisions, and similarly named book exit thresholds.
Related: [Database Transactions](database-transactions.md), [DB Migration System](db-migration-system.md), [Book-Keyed Execution Model](../adr/010-book-keyed-execution-model.md)

## Purpose

This is a living current-state reference, not an implementation plan. It describes what the schema,
repositories, and production writers do today and labels incomplete runtime coverage explicitly.

`equity_snapshots`, `daily_metrics`, and `risk_snapshots` all hang off the
`accounts → books` hierarchy but each sits at a different grain and uses a
different account-level read strategy. Several columns also share names or
suffixes while meaning different things (period, grain, or units). This note is
the single place that pins down what each column means and how the account view
is derived. Reach for it before adding a consumer, a metric, or a rollup.

## Overview — the grain map

One account owns many books; a book is the execution primitive (see
[ADR 010](../adr/010-book-keyed-execution-model.md)). The four tables land at
different grains:

| Table | Stored grain | Uniqueness | Account-level read |
|---|---|---|---|
| `equity_snapshots` | **book** + `snapshot_time` | `(book_id, snapshot_time)` | SQL rollup view: `SUM` of balances across the account's books per `snapshot_time` |
| `daily_metrics` | **book** + `metric_date` | `(book_id, metric_date)` | JOIN filter that returns **one row per book** (no aggregation) |
| `risk_snapshots` | **account** + `snapshot_time` | `(account_id, snapshot_time)` | native; no book breakdown exists |
| `risk_decisions` | **account** (+ nullable `book_id`) | non-null `(book_id, account_id)` must match `books(id, account_id)` | native |

Consequences worth knowing before you build on them:

- **`equity_snapshots` account rollup carries no identity.** In the rollup
  select (`repositories/snapshots.py`), `id` and `book_id` are coupled: both are
  real on a single-book read, and both are `NULL` on a multi-book aggregate. A
  rollup record is therefore not an addressable row, and `EquitySnapshotRecord.id`
  is `int | None` so misuse fails loudly instead of silently targeting `MIN(id)`.
- **`daily_metrics` has no account rollup.** Percentages don't sum, so
  `fetch_book_rows_for_account` returns each book's row (the name says so).
  "Account daily metrics" is therefore N rows per date for an N-book account,
  not one aggregated row.
- **`risk_snapshots` is account-only by design** — gross/net exposure and
  concentration are portfolio-wide properties. There is no per-book risk row.

## equity_snapshots

Book-keyed point-in-time balance snapshots. Written via
`EquitySnapshotRepository.insert_for_book` (or `insert`, which resolves the
account's default book).

| Column | Type | Meaning |
|---|---|---|
| `book_id` | INT | Owning book. `NULL` only on synthetic account-rollup **read** rows (never stored NULL). |
| `snapshot_time` | TEXT (ISO-8601 UTC) | Instant of the snapshot. Ordering relies on lexicographic ISO. |
| `cash` | REAL | Settled cash balance. |
| `market_value` | REAL | Marked value of open positions. |
| `equity` | REAL | Total equity. Stored as `cash + market_value`; a **derived** value frozen at write time (no DB-level invariant enforces it). |
| `realized_pnl` | REAL | Cumulative realized P&L at the snapshot instant. |
| `unrealized_pnl` | REAL | Open-position P&L at the snapshot instant. |

## daily_metrics

Book-keyed per-day performance metrics, upserted on `(book_id, metric_date)`
via `DailyMetricsRepository.upsert`. The production writer is
`services/analysis/daily_metrics.py::write_daily_metrics_for_account`, run from
`snapshot_account` right after the day's equity snapshot is written (so it lands
in the daily paper-trading workflow's snapshot step and on any manual `snapshot`).
Every metric column is nullable; the writer populates the columns derivable from
stored daily activity and leaves the rest `NULL` on purpose (see the column notes
and Implementation gaps).

| Column | Type | Period | Meaning |
|---|---|---|---|
| `metric_date` | TEXT (ISO date) | the day | Calendar day the metrics summarize. |
| `return_pct` | REAL | 1 day | Book return for `metric_date`, in **percent**. |
| `drawdown_pct` | REAL | 1 day | Peak-to-trough decline over the day, in percent. Distinct from `risk_snapshots.drawdown_pct` (account grain, point-in-time). |
| `turnover_pct` | REAL | 1 day | Traded notional relative to equity, in percent. |
| `slippage_bps` | REAL | 1 day | Average execution slippage, in **basis points**. Same concept as `orders`/`backtest_*` slippage; keep the computation consistent. |
| `hit_rate` | REAL | 1 day | Fraction of winning trades, `0.0–1.0` (not a percent). |
| `expectancy` | REAL | 1 day | Average P&L per trade, in account currency. Writer-defined; formula not yet pinned in a shared helper. |
| `risk_adjusted_score` | REAL | 1 day | Composite risk-adjusted performance score. **Which** measure (Sharpe/Sortino/custom) is writer-defined and not yet pinned — see open items. |
| `trade_count` | INT | 1 day | Number of trades that day. |
| `fees_total` | REAL | 1 day | Total commissions/fees for the day, in account currency. |

## risk_snapshots

Account-keyed point-in-time risk snapshot, unique on
`(account_id, snapshot_time)`. Exposure fields are computed by
`services/execution/risk.py::compute_current_exposure_snapshot`
over the account's positions and books; concentration caps themselves live in
`RiskGateConfig` (`domain/risk_gate.py`).

| Column | Type | Meaning |
|---|---|---|
| `gross_exposure` | REAL | Σ `abs(market_value)` across all account positions (long + short magnitude), in account currency. |
| `net_exposure` | REAL | Σ `market_value` (signed: long − short), in account currency. |
| `max_symbol_concentration_pct` | REAL | Largest single-symbol exposure ÷ total book equity. **A fraction (0–1), despite the `_pct` suffix.** |
| `max_sector_concentration_pct` | REAL | Largest single-sector exposure ÷ total book equity. **A fraction (0–1), despite the `_pct` suffix.** |
| `drawdown_pct` | REAL, nullable | Reserved. The auto-trading writer currently records `NULL`. |
| `leverage_proxy` | REAL, nullable | Reserved leverage approximation (hence "proxy"). Auto-trading writer currently records `NULL`. |
| `daily_loss_pct` | REAL, nullable | Reserved day-loss figure (a 1-day drawdown). Auto-trading writer currently records `NULL`. |
| `kill_switch_triggered` | INT (0/1) | Whether the risk kill-switch fired at this snapshot. |
| `risk_payload_json` | TEXT (JSON) | **Supplementary** detail only. The typed columns above are canonical; the JSON carries extra context and must not be the sole source for a value that has a column. |

## books exit-threshold columns

`books` carries two pairs of exit thresholds that read almost identically. They
are **not** interchangeable — each pair applies to a different `instrument_mode`:

| `instrument_mode` | Profit target | Loss cap |
|---|---|---|
| `equity` | `take_profit_pct` | `stop_loss_pct` |
| `leaps` (options) | `option_profit_take_pct` | `option_max_loss_pct` |

The option pair was renamed from `profit_take_pct` / `max_loss_pct` (revision
`0011`) into the `option_*` column family so the instrument it belongs to is
legible from the name. The equity pair drives `domain/auto_trading_policy.py`;
the option pair is configurable and persisted but has no production execution consumer yet.

## Boundaries

- **Grain is fixed per table.** New runtime performance/risk work is book-keyed
  unless it is genuinely account-wide (exposure, concentration) — see
  [ADR 010](../adr/010-book-keyed-execution-model.md). Do not add a per-book
  `risk_snapshots` variant or an account-mode execution path.
- **Timestamps are ISO-8601 UTC TEXT.** Ordering and range filters rely on
  lexicographic comparison; always write zero-padded UTC ISO strings.
- **`_pct` is not a promise of percent.** `hit_rate` and the two concentration
  columns are fractions (0–1); the `*_return_pct`, `drawdown_pct`, and
  `turnover_pct` fields are percents. Check this table before assuming units.
- **Denormalized running state exists.** `books.current_cash` /
  `current_equity` duplicate the latest equity snapshot; nothing reconciles the
  two. Treat snapshots as the historical source of truth.

## Implementation gaps

- `daily_metrics` is populated by the production writer for the columns derivable from stored daily
  activity — `return_pct`, `turnover_pct`, `slippage_bps`, `trade_count`, `fees_total`. The remaining
  four are written `NULL` because their inputs are not stored at this grain: `drawdown_pct` needs
  intraday equity; `hit_rate` and `expectancy` need **per-trade** realized P&L (fills store only
  qty/price/commission, and realized P&L is stored per-book/cumulative); `risk_adjusted_score` needs a
  return series (a trailing-window writer could add it later). Populating `hit_rate`/`expectancy` would
  most cleanly come from persisting a per-fill `realized_pnl_delta` (as `rotation_decisions` already
  does), a schema change.
- `risk_snapshots.drawdown_pct`, `leverage_proxy`, and `daily_loss_pct` are
  columns without a populating writer (recorded `NULL` today).
- `books.option_profit_take_pct` and `option_max_loss_pct` have configuration and persistence
  surfaces but no production options-execution consumer.

## Related Docs

- [Database Transactions](database-transactions.md) — atomic multi-write pattern
- [DB Migration System](db-migration-system.md) — how columns like these change
- [Book-Keyed Execution Model (ADR 010)](../adr/010-book-keyed-execution-model.md)
