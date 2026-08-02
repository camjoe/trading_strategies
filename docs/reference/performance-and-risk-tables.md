# Performance and Risk Tables

Type: notes
Status: Active
Created: 2026-07-21
Last Reviewed: 2026-08-02
Purpose: Record where reading `equity_snapshots`, `daily_metrics`, `risk_snapshots`, `risk_decisions`, and the `books` exit-threshold columns naively produces a wrong answer — mismatched grain, misleading units, reused names, and columns with no data.

## Purpose

`db-schema.md` says what each table is for; `python -m scripts.data_ops.describe_db_schema`
gives the live columns and types. Neither can tell you that `hit_rate` is a fraction while
`return_pct` beside it is a percent, or that `drawdown_pct` means two different things in two
tables. This file is only for the traps. Read it before adding a consumer, a metric, or a
rollup.

## Grain and account-level reads

One account owns many books; a book is the execution primitive
([ADR 010](../adr/010-book-keyed-execution-model.md)). The four tables sit at different
grains, and the account-level read differs accordingly:

| Table | Stored grain | Uniqueness | Account-level read |
|---|---|---|---|
| `equity_snapshots` | **book** + `snapshot_time` | `(book_id, snapshot_time)` | SQL rollup view: `SUM` of balances across the account's books per `snapshot_time` |
| `daily_metrics` | **book** + `metric_date` | `(book_id, metric_date)` | JOIN filter returning **one row per book** (no aggregation) |
| `risk_snapshots` | **account** + `snapshot_time` | `(account_id, snapshot_time)` | native; no book breakdown exists |
| `risk_decisions` | **account** (+ nullable `book_id`) | non-null `(book_id, account_id)` must match `books(id, account_id)` | native |

- **`daily_metrics` has no account rollup.** Percentages don't sum, so
  `fetch_book_rows_for_account` returns each book's row. "Account daily metrics" is therefore
  N rows per date for an N-book account, not one aggregated row.
- **The `equity_snapshots` account rollup carries no identity.** In the rollup select
  (`repositories/snapshots.py`), `id` and `book_id` are both real on a single-book read and
  both `NULL` on a multi-book aggregate. A rollup record is not an addressable row, and
  `EquitySnapshotRecord.id` is `int | None` so misuse fails loudly instead of silently
  targeting `MIN(id)`.
- **`risk_snapshots` is account-only by design** — gross/net exposure and concentration are
  portfolio-wide properties. There is no per-book risk row.

## Units — `_pct` is not a promise of percent

| Column | Actual unit |
|---|---|
| `daily_metrics.hit_rate` | fraction `0.0–1.0` |
| `risk_snapshots.max_symbol_concentration_pct` | fraction `0–1`, despite the suffix |
| `risk_snapshots.max_sector_concentration_pct` | fraction `0–1`, despite the suffix |
| `daily_metrics.slippage_bps` | basis points — same concept as `orders`/`backtest_*` slippage; keep the computation consistent |
| `daily_metrics.return_pct` / `drawdown_pct` / `turnover_pct` | percent |
| `risk_snapshots.drawdown_pct` | percent (`<= 0`) |
| `daily_metrics.expectancy`, `fees_total`, `risk_snapshots.gross_exposure` / `net_exposure` | account currency |

## Same name, different meaning

- **`drawdown_pct`** — `daily_metrics.drawdown_pct` is **book** grain, peak-to-trough over a
  single day. `risk_snapshots.drawdown_pct` is **account** grain, point-in-time:
  `current_equity / peak_equity - 1`, where `peak_equity` is the account's highest equity
  ever recorded (`EquitySnapshotRepository.fetch_max_equity`), including today.
- **`books` exit thresholds** — two pairs that read almost identically and are **not**
  interchangeable; each applies to a different `instrument_mode`:

  | `instrument_mode` | Profit target | Loss cap |
  |---|---|---|
  | `equity` | `take_profit_pct` | `stop_loss_pct` |
  | `leaps` (options) | `option_profit_take_pct` | `option_max_loss_pct` |

  The option pair was renamed from `profit_take_pct` / `max_loss_pct` (revision `0011`) into
  the `option_*` family so the instrument is legible from the name.

## Columns that are not what they look like

- **`equity_snapshots.equity`** is derived — stored as `cash + market_value` and frozen at
  write time. No DB-level invariant enforces it.
- **`risk_snapshots.risk_payload_json`** is **supplementary** detail. The typed columns are
  canonical; the JSON must not be the sole source for a value that has a column.
- **`books.current_cash` / `current_equity`** duplicate the latest equity snapshot, and
  nothing reconciles the two. Treat snapshots as the historical source of truth.
- **`daily_metrics.risk_adjusted_score`** is a trailing **annualized Sharpe ratio** over the
  book's recent daily `return_pct` series (`mean / population-std × √252`, risk-free 0 — the
  convention in `backtesting/domain/metrics.py::sharpe_ratio`), over the last ≤20 scored
  sessions including the day. Not a single-day figure like its neighbours.

## Columns with no data, or not yet

`daily_metrics` is upserted on `(book_id, metric_date)` by
`services/analysis/daily_metrics.py::write_daily_metrics_for_account`, run from
`snapshot_account` right after the day's equity snapshot. Every metric column is nullable and
the writer leaves some `NULL` on purpose:

| Column | State |
|---|---|
| `daily_metrics.drawdown_pct` | Always `NULL` — needs intraday equity, which is not persisted at this grain |
| `risk_snapshots.daily_loss_pct` | Always `NULL` — no writer. Same single-day gap; a trailing-history peak cannot stand in for one day's figure |
| `daily_metrics.hit_rate` / `expectancy` | Populated only for orders created after revision `0020` (from `orders.realized_pnl_delta`); no historical backfill. `hit_rate` is also `NULL` on a day with no closing trades |
| `daily_metrics.risk_adjusted_score` | `NULL` until at least 10 returns exist, and when the returns have zero dispersion; no backfill |
| `books.option_profit_take_pct` / `option_max_loss_pct` | Configuration and persistence exist; no production options-execution consumer |

`risk_snapshots.drawdown_pct` and `leverage_proxy` are written by
`persist_book_risk_snapshot`; `leverage_proxy` is `gross_exposure / total_equity`, `NULL` when
equity is zero. Exposure fields come from
`services/execution/risk.py::compute_current_exposure_snapshot`; the concentration caps
themselves live in `RiskGateConfig` (`domain/risk_gate.py`).

## Boundaries

- **Grain is fixed per table.** New runtime performance/risk work is book-keyed unless it is
  genuinely account-wide (exposure, concentration) — see
  [ADR 010](../adr/010-book-keyed-execution-model.md). Do not add a per-book `risk_snapshots`
  variant or an account-mode execution path.
- **Timestamps are ISO-8601 UTC TEXT.** Ordering and range filters rely on lexicographic
  comparison; always write zero-padded UTC ISO strings.

## Related Docs

- [Database Transactions](database-transactions.md) — atomic multi-write pattern
- [DB Migration System](db-migration-system.md) — how columns like these change
- [Book-Keyed Execution Model (ADR 010)](../adr/010-book-keyed-execution-model.md)
