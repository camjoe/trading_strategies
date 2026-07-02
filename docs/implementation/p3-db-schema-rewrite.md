# Implementation Guide — P3: Greenfield DB schema rewrite (the spine)

Type: implementation
Status: Ready (large; multi-commit)
Initiative: P3 (DB schema rewrite, option B)
Estimate: L
Created: 2026-07-01
Last Reviewed: 2026-07-01
Related: [Plan](../plan.md), [Decisions](../decisions.md),
[DB Schema Rewrite Spec](../db-schema-rewrite-spec.md), [DB Schema Target](../db-schema-target.md),
[Architecture Conventions](../architecture/architecture-conventions.md)

> Follows the [implementation template](p2-evaluation-contract-tests.md). P3 is **large** — it is one
> initiative but built in ordered phases, each its own green commit. An agent should work top-to-bottom.

## 1. Objective

Replace the current 25-table schema with the clean trading-unit schema in
[db-schema-target.md](../db-schema-target.md) — **greenfield, no data migration** (old data is
dropped). Deliver the schema, models, repositories, a seeded strategy catalog, and re-pointed
read-side consumers. This is the **spine** P4/P6/P7 build on.

### Definition of Done
- [ ] Fresh DB init creates every table in the target with its constraints, indexes, and the two
      partial-unique invariants (default unit; open assignment).
- [ ] A passive model exists per table; a repository exists per table (SQL only).
- [ ] The strategy catalog is seeded from the 14 current `STRATEGY_REGISTRY` entries (primitive + knobs).
- [ ] Read-side consumers (evaluation evidence, backtesting, reporting, analysis) read the new tables
      via `strategy_id`/`unit_id`.
- [ ] `python -m scripts.run_checks --profile ci` green; `python -m scripts.data_ops.describe_db_schema`
      shows the target; layer check clean.
- [ ] Plan P3 status updated.

## 2. Preconditions
- **P1 (execution loop) landed first** — it is schema-agnostic logic; P3 then re-points its
  persistence. Confirm P1 is merged, or coordinate.
- Decisions locked: [D2/D3/D7](../decisions.md#d2) (rewrite-first, real default unit), [D4](../decisions.md#d4)
  (params split — settle the account/unit **settings shape** at the start of Phase A), [D5](../decisions.md#d5)
  (strategy = primitive + knobs), [D6](../decisions.md#d6) (score columns).
- `./.venv` exists; you can run the migration/DB-init tooling.

## 3. Guardrails
- Use the venv interpreter; respect layering (`models` lowest → `repositories` SQL-only → `services`).
- **Greenfield:** dropping old data is intended and pre-approved (see the data-loss assessment). Still
  take one fresh `local/db_backups/` snapshot first (see [Developer Notes](../developer-notes.md)).
- **Enforce the invariants** ([target schema](../db-schema-target.md) → Conventions): the two partial-
  unique indexes in DDL; order↔unit↔account integrity and strategy-immutability in the repositories.
- **Never** set `live_trading_enabled` in DDL/seed/fixtures (human-only gate).
- Use the `db-migration` skill / existing migration framework for DDL — do **not** hand-roll a second
  migration path (ADR/conventions).

## 4. Branch & commit strategy
- Dedicated branch, e.g. `features/p3-db-schema-rewrite`.
- **One commit per phase below** (A→E), each after its checks are green. Never commit on red.
- Commit message format per the template (summary + body + `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`).

## 5. Build plan (ordered phases)

### Phase A — Schema DDL & init  *(commit: "P3: clean schema DDL")*
- Define all target tables + constraints + indexes + the two partial-unique invariants in the schema
  init (`src/infrastructure/database/` — schema/DDL module; see `docs/reference/db-migration-system.md`).
- Turn on `PRAGMA foreign_keys = ON` in the connection setup if not already.
- Settle the **D4 account/unit settings shape** here (typed columns on `accounts`/`trading_units` vs a
  small config table) and encode it.
- Verify with `python -m scripts.data_ops.describe_db_schema` against a fresh DB.

### Phase B — Models  *(commit: "P3: models for the clean schema")*
- One passive dataclass per table under `src/trading/models/<area>/` (one contract per file; no logic;
  imports only from `common`/`models`). Follow `*Record`/`*Insert`/`*Config` lifecycle naming.

### Phase C — Repositories  *(commit: "P3: repositories for the clean schema")*
- One repository per table under `src/trading/repositories/` (SQL reads/writes only; `fetch_*` /
  `insert_*` / `update_*`). Encode the service-enforced invariants (open-assignment, order↔unit↔account,
  strategy-immutability) as repository guards where practical.

### Phase D — Primitive catalog + seed  *(commit: "P3: primitive catalog + seed strategy catalog")*
- Extract the code **primitive catalog** from `src/trading/domain/strategy_signals.py` (the signal-fn
  map + each primitive's knob schema) — the code half of D5. (This is shared with P6/4a.)
- Seed the `strategies` table with the 14 current `STRATEGY_REGISTRY` entries (primitive + their
  `default_params` as knobs). Provide a CLI/data-op to (re)seed.
- Bootstrap: create accounts + their default `trading_units` from profiles/CLI.

### Phase E — Re-point read-side consumers  *(commit: "P3: re-point evaluation/backtest/reporting reads")*
- `src/trading/services/evaluation/evidence.py` — read unit-keyed snapshots/metrics + `strategy_id`.
- `src/trading/backtesting/` repositories + services — `strategy_id` FK instead of name strings.
- `src/trading/services/reporting/` and `services/analysis/performance.py` — unit-keyed reads.
- **Out of scope here (P4):** the execution/submission/rotation/accounting **write** services on the
  operational tables (`orders`, `positions`, `ledger`, `equity_snapshots`). P3 leaves those tables
  created and empty; P4 wires the writers.

## 6. Areas of code expected to be edited (per table)

| Table | Model (`models/`) | Repository (`repositories/`) | Primary consumers to touch |
|---|---|---|---|
| `accounts` | `accounts/` | `accounts.py` | `services/accounts`, evaluation, most reads |
| `trading_units` | `units/` (new) | `trading_units.py` (new) | execution (P4), evaluation, reconciliation |
| `strategies` | `strategy/` | `strategies.py` (new) | `domain/strategy_signals` loader (P6/4a), rotation |
| `feature_providers` | `strategy/` or new | `feature_providers.py` (new) | interface wiring (P6/4b) |
| `unit_strategy_assignments` | `units/` | `unit_assignments.py` (new) | rotation (P4) |
| `rotation_decisions` | `sleeves/`→`units/` | `rotation_decisions.py` | rotation (P4) |
| `orders` | `orders/` | `orders.py` (new; unifies broker+sleeve) | execution (P4), reconciliation |
| `order_fills` | `orders/` | `order_fills.py` | execution (P4) |
| `positions` | `units/` | `positions.py` (new) | execution/state (P4), risk |
| `ledger` | `units/` | `ledger.py` (new) | accounting (P4) |
| `equity_snapshots` | `portfolio/` | `snapshots.py` | evaluation evidence, reporting |
| `daily_metrics` | `portfolio/` | `daily_metrics.py` | `analysis/performance`, reporting, rotation |
| `risk_snapshots`/`risk_decisions` | `sleeves/`→`units/` | risk repos | `runtime_sleeve_risk` (P4) |
| `promotion_reviews`/`_events` | `promotion/` | promotion repos | `services/promotion` |
| `backtest_*` / `walk_forward_*` | `backtesting/` models | `backtesting/repositories/` | backtesting services, evaluation evidence |

Retired: `strategy_param_sets` (+ its repo/model), `sleeve_*` tables (+ repos) — folded into the above.

## 7. Validation
Run from repo root with the venv interpreter, after each phase:
```
.venv\Scripts\python.exe -m scripts.data_ops.describe_db_schema      # confirms target tables/indexes
.venv\Scripts\python.exe -m scripts.checks.layer_check
.venv\Scripts\python.exe -m scripts.checks.mypy_check
.venv\Scripts\python.exe -m scripts.run_checks --profile quick        # per-phase
.venv\Scripts\python.exe -m scripts.run_checks --profile ci           # final
```
Add repository tests per table (round-trip insert/fetch; the invariant guards: default-unit uniqueness,
open-assignment uniqueness, strategy-immutability rejection).

## 8. Failure handling
- A read consumer can't be re-pointed without its writer (operational tables) → that's the P3/P4
  boundary; leave the write path to P4 and note it, don't pull P4 forward silently.
- Invariant can't be expressed in SQLite (e.g. order↔unit↔account) → enforce in the repository and
  cover with a test; record the choice.
- Any check red → fix or stop and report; do not commit.

## 9. Handoff / PR
- Push the branch; open a PR summarizing the phases + validation, or hand back per operator preference.
- Update [plan.md](../plan.md): P3 status; check off the "define primitive catalog" and "seed strategy
  catalog" tasks.

## 10. Out of scope
- P4 execution/rotation/accounting **write** services (operational tables).
- P6 strategy loader wiring beyond the primitive catalog extraction + seed; P7 parameter view/CLI.
- The dedicated `decision_snapshots` table (deferred to P10 per D6).

## 11. Final report (per `AGENTS.md` output style)
- **Developer verification:** `describe_db_schema` output; a seeded-catalog listing; which reads re-pointed.
- **Validation run:** the §7 commands + results.
- **Cleanup/robustness notes:** retired tables/repos removed; invariants covered by tests.
