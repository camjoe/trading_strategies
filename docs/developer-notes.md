# Developer Notes & Task Tracker

Type: notes
Status: Active
Created: 2026-07-01
Last Reviewed: 2026-07-01
Purpose: Developer-facing working notes, pre-implementation checks, and a quick task/timeline snapshot
for how much work is left — a sanity check for the same developer picking work back up.
Related: [Overview](overview.md), [Roadmap](roadmap.md),
[DB Schema Rewrite Spec](db-schema-rewrite-spec.md), [DB Schema Target (WIP)](db-schema-target.md),
[Sleeves & Accounts Convergence Plan](sleeves-accounts-convergence.md)

> The roadmap and overview are the source of truth for scope and priority. This doc is a quick
> glance for the developer: what to check before starting, durable gotchas, and how much is left.

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
- **Live/paper does not run strategy signals yet** (Roadmap Now #3). The paper trader is a legacy
  random/style-biased placeholder; strategy `signal_fn`s run only in backtests. Do not assume paper
  results reflect the strategies until the execution loop is closed.
- **Parameter sets are not wired into signals** — `strategy_param_sets` is stored/governed only;
  backtests use code `default_params`. "Different parameters" is not yet a real lever.
- **`shadow_evaluation` is thin post-1b** — its separate challenger-scoring path is gone; it's a
  rename/absorb candidate (Roadmap Later #4).
- **`mypy` must be run via the project runner** — `python -m scripts.checks.mypy_check` (ad-hoc
  `mypy <file>` fails to resolve the `src/` layout and reports false import errors).
- **Two rotation paradigms still exist** — account-episode vs sleeve champion/challenger. The
  decision-score contract is shared for sleeve rotation (1a/1b); account rotation is not yet migrated.

## Task / timeline snapshot (as of 2026-07-01)

Glance-level status. Authoritative detail lives in [roadmap.md](roadmap.md). Order follows the
overview's "Direction & plan".

| # | Initiative | Status | Notes |
|---|---|---|---|
| 1 | Now #3 — Close the execution loop (keystone) | ☐ Not started | E1 run signals in live/paper; E2 apply param sets. Highest priority. |
| 2 | Now #1 — Unified evaluation | ◑ In progress | 1a ✅, 1b ✅, 1c ☐ (cross-surface regression tests) |
| 3 | Now #4 — Plug-and-play strategy & provider catalog | ☐ Not started | 4a data-driven strategy registry; 4b feature-provider registry. Depends on #3. |
| 4 | Now #2 — Converge accounts & sleeves | ☐ Not started | 2a submission service, 2b rotation, 2c accounting. Gated by A/B decision. |
| 5 | DB schema rewrite (convergence option B) | ✎ Spec drafted | Not scheduled; greenfield/no migration. See spec + target docs. |
| 6 | Next #1 — Email notifications | ☐ Not started | Additive. |
| 7 | Next #2 — Unified parameter source | ☐ Not started | Service-first; UI optional. |
| 8 | Later #1 — Adaptive learning | ☐ Deferred | Depends on decision-score contract. |
| 9 | Later #2 — Portfolio risk rollup | ☐ Deferred | Service-first. |
| 10 | Later #3 — Strategy parameter optimization | ☐ Deferred | 3a storage guardrail first. |
| 11 | Later #4 — Decisioning legibility & naming pass | ☐ Deferred | Rename `shadow_evaluation`; disambiguate "rotation". |

Legend: ✅ done · ◑ in progress · ✎ spec/plan only · ☐ not started.

### Recommended next action

Close the execution loop (Now #3) — it is the keystone; the evaluate → rotate → trade loop is
premature until the live path actually runs the selected strategy and params. Finish 1c alongside or
just after.
