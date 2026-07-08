# Developer Notes & Checks

Type: notes
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-05
Purpose: Developer-facing working notes, gotchas, and pre-implementation checks — a sanity check for
the same developer picking work back up. Current status lives in [status.md](status.md).
Related: [Overview](overview.md), [Status](status.md), [Decisions](decisions.md),
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md), [DB Schema Target](db-schema-target.md)

> [status.md](status.md) is the source of truth for scope/status; [decisions.md](decisions.md) for
> open decisions. This doc is what to check before starting and durable gotchas.

## Pre-implementation checks

### Before the database rewrite (completed 2026-07-05 — retained as the P3 pre-flight record)

- [ ] **Re-read and confirm the DB spec** — [db-schema-rewrite-spec.md](db-schema-rewrite-spec.md)
      and the standalone [db-schema-target.md](db-schema-target.md). Confirm the target still matches
      goals before writing any DDL.
- [ ] **Check accounts for parameters worth keeping** — before dropping data, inspect the current
      accounts for any parameters you actually tuned and liked (stops, sizing, rotation settings,
      option config). Params were mostly arbitrary/profile defaults and `strategy_param_sets` is
      empty, so likely nothing — but confirm and jot down anything you want to re-create.
      Quick check: `.venv/Scripts/python.exe -m scripts.data_ops.describe_db_schema --source live`,
      and query `accounts` on `local/paper_trading.db`.
- [ ] **Confirm audit trails are still empty** — re-check `promotion_reviews` /
      `promotion_review_events` row counts; if any human review history has accrued since the
      2026-07-01 assessment, decide whether to preserve it.
- [ ] **Settle the remaining D4 tail** — the account/book settings shape (typed columns vs a small
      typed config table per concern), decided at the start of P3 Phase A. The other rewrite
      decisions (D2/D3/D5/D6/D7) were resolved 2026-07-01 — see [decisions.md](decisions.md).
- [ ] **Keep a fresh backup** — `local/db_backups/` already holds snapshots; take one more before
      dropping.

### Before any `src/trading/` change (standing checks)

- [ ] Read `docs/architecture/architecture-conventions.md` (layering + interface primacy) if touching
      services/domain boundaries.
- [ ] Use the repo venv interpreter (`.venv/Scripts/python.exe` on Windows). Never system Python.
- [ ] After edits, run the matching suite (`python -m scripts.checks.run_suite <suite>`), then
      `python -m scripts.run_checks quick` (repo safety + Python lint/type/test checks).
- [ ] Build capability at the **service/CLI layer first**; the UI is an optional consumer. Never make
      a capability reachable only through the UI.

## Developer notes (durable gotchas)

- **CRLF warnings on commit are harmless** — the repo enforces line endings; `git` prints
  "CRLF will be replaced by LF" on commit. Not an error.
- **Live/paper runs strategy signals as of P1 (2026-07-03)** — selection goes through the shared
  `evaluate_signal(...)`; trades happen only on signals (no forced minimum, `--max-trades` cap).
  Paper results **before** that date reflect the old random placeholder — do not read them as
  strategy evidence.
- **Strategy knobs are not data yet** — `resolve_strategy_params` (the P1 seam) still returns the
  registry `default_params`; `strategy_param_sets` remains stored/governed only. The data-knob
  layer lands with the rewrite (P3/D4/D5). "Different parameters" is not yet a real lever.
- **`shadow_evaluation` is thin post-1b** — its separate challenger-scoring path is gone; it's a
  rename/absorb candidate (Plan P5).
- **`mypy` must be run via the project runner** — `python -m scripts.checks.python.mypy_check` (ad-hoc
  `mypy <file>` fails to resolve the `src/` layout and reports false import errors).
- **Two rotation paradigms still exist** — account-episode vs sleeve champion/challenger. The
  decision-score contract is shared for sleeve rotation (1a/1b); account rotation is not yet migrated.
- **The book schema is live but reached through bridges (P3 done, P4 pending).** The clean tables
  (`books`, `book_*_settings`, `orders`, `positions`, `ledger`, book-keyed `equity_snapshots` /
  `daily_metrics` / `rotation_decisions`, order-keyed `order_fills`, `strategy_id`-keyed backtests)
  are the storage now, but the legacy account/sleeve access paths reach them via
  `trading/repositories/book_bridge.py` (account→default book, sleeve→bridging book, label→catalog
  row, broker-order→orders mirror). These bridges — and the account/sleeve-keyed repository APIs —
  retire when P4 builds the converged write services.
- **Backtest strategy labels are canonical keys (P3/E5)** — `backtest_runs`/`walk_forward_groups`
  key `strategy_id`; reports/leaderboards show the catalog `strategy_key` (e.g. `trend`), not the
  original alias (`trend_v1`). See [D14](decisions.md#d14).

## Where to look

- **Current status / next action per workstream** → [status.md](status.md) (the single source).
- **Open decisions ("what needs defining")** → [decisions.md](decisions.md).
- **Finished work + progress logs** → [history/](history/README.md).
  Sequence P4's shared submission service (2a) first to shorten the runtime pause.
