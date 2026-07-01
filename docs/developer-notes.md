# Developer Notes & Checks

Type: notes
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: Developer-facing working notes, gotchas, and pre-implementation checks — a sanity check for
the same developer picking work back up. Tasks/order/status/timelines live in [plan.md](plan.md).
Related: [Overview](overview.md), [Plan](plan.md), [Decisions](decisions.md),
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md), [DB Schema Target (WIP)](db-schema-target.md),
[Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md)

> [plan.md](plan.md) is the source of truth for scope/order/status; [decisions.md](decisions.md) for
> open decisions. This doc is what to check before starting and durable gotchas.

## Pre-implementation checks

### Before the database rewrite (if/when we execute it)

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
- [ ] **Resolve the open decisions** in the spec (default unit real-vs-virtual, `parameters` model
      shape, whether to persist evaluation/decision snapshots, strategy catalog granularity).
- [ ] **Keep a fresh backup** — `local/db_backups/` already holds snapshots; take one more before
      dropping.

### Before any `src/trading/` change (standing checks)

- [ ] Read `docs/architecture/architecture-conventions.md` (layering + interface primacy) if touching
      services/domain boundaries.
- [ ] Use the repo venv interpreter (`.venv/Scripts/python.exe` on Windows). Never system Python.
- [ ] After edits, run the matching suite (`python -m scripts.checks.run_suite <suite>`), then
      `python -m scripts.run_checks --profile quick` (layer + ruff + mypy + targeted tests).
- [ ] Build capability at the **service/CLI layer first**; the UI is an optional consumer. Never make
      a capability reachable only through the UI.

## Developer notes (durable gotchas)

- **CRLF warnings on commit are harmless** — the repo enforces line endings; `git` prints
  "CRLF will be replaced by LF" on commit. Not an error.
- **Live/paper does not run strategy signals yet** (Plan P1). The paper trader is a legacy
  random/style-biased placeholder; strategy `signal_fn`s run only in backtests. Do not assume paper
  results reflect the strategies until the execution loop is closed.
- **Parameter sets are not wired into signals** — `strategy_param_sets` is stored/governed only;
  backtests use code `default_params`. "Different parameters" is not yet a real lever.
- **`shadow_evaluation` is thin post-1b** — its separate challenger-scoring path is gone; it's a
  rename/absorb candidate (Plan P5).
- **`mypy` must be run via the project runner** — `python -m scripts.checks.mypy_check` (ad-hoc
  `mypy <file>` fails to resolve the `src/` layout and reports false import errors).
- **Two rotation paradigms still exist** — account-episode vs sleeve champion/challenger. The
  decision-score contract is shared for sleeve rotation (1a/1b); account rotation is not yet migrated.

## Where to look

- **Tasks / order / status / timelines** → [plan.md](plan.md) (the status board + Current cycle
  sequencing are the single source).
- **Open decisions ("what needs defining")** → [decisions.md](decisions.md).
- **Recommended next action** → close the execution loop (Plan P1, the keystone), then finish 1c.
