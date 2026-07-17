# Database Cleanup Roadmap

Type: notes
Status: Active
Created: 2026-07-13
Last Reviewed: 2026-07-16
Purpose: Complete inventory of database schema cleanup, fixes, and improvements, broken into
sequenced work items for the full-schema cleanup effort.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md)

## Purpose

This is the working plan for bringing the database schema to its target clean state. It inventories
every known schema issue — legacy dual-ownership columns, the transitional trade-history bridge,
soft references, missing indexes, and documentation gaps — as separate work items with per-item
status, blocking readers, and migration notes. Use it to pick, sequence, and scope cleanup branches.

## Overview

The schema is moving toward a book-owned execution model: `accounts` holds identity and custody
metadata, `books` are the execution units, and execution behavior lives on books and typed settings
tables. The move is mid-transition, and the transition itself is the main risk: several settings
groups currently have **two writable homes** (account columns and book settings tables) with
readers still on the account side. Trade history similarly has two parallel representations
(`trades` and `orders`/`order_fills`) joined by an explicit runtime bridge.

Working principles for every item below:

- Typed tables and columns, never generic EAV/category/value storage.
- One numbered Alembic migration per ownership group, following the `0002` rebuild pattern:
  self-contained literal DDL, explicit column copy list, table rebuild, `PRAGMA
  foreign_key_check`, reversible downgrade (ADR 015).
- **Atomic cutovers**: when a group moves, one branch moves the readers, backfills the new home
  from the old values in the migration, and drops the old columns together. No long-lived window
  where both homes are writable.
- Regenerate `docs/reference/database-diagram-viewer.html` and update `docs/reference/db-schema.md`
  after each schema change.

## Open Decisions

These need explicit decisions before their dependent work items. Each has a recommendation; none
is decided yet.

### OD1 — Target shape for book settings: 1:1 tables vs columns on `books`

`book_execution_settings` and `book_option_settings` are 1:1 tables, but goals and
`trade_universes` live directly on `books`. Two patterns for the same category of data.

- **Option A (fold into `books`)**: move execution + option columns onto `books`. A row always
  exists, DDL defaults always apply, no missing-row fallback logic, fewer joins. Matches how goals
  already work.
- **Option B (keep 1:1 tables)**: keeps `books` narrow and namespaced; costs missing-row semantics
  (readers must define what "no settings row" means) and join fan-out.
**DECIDED 2026-07-16: Option A** — execution and option settings become columns on `books`;
`book_execution_settings` and `book_option_settings` are dropped by the A2/A3 migrations after
their values are folded in. `book_rotation_settings` stays a separate table (large, coherent,
sparse). The hesitation considered — separate tables might make future settings-learning
easier — was judged over-engineering: a learner reads settings by `book_id` either way, and a
learning system that *proposes* setting variants would need its own candidate/experiment table
regardless (live settings tables hold current state, not candidates).

### OD2 — Goals: account default vs book-owned

**DECIDED 2026-07-16: drop the account-level goal columns** — `goal_min_return_pct`,
`goal_max_return_pct`, `goal_period` are book-owned; the account copies are leftover state
with CRUD/display readers only. (`trade_universes` was originally part of this decision but
was carved out into OD6 after reader verification showed it is a live runtime read.)

### OD6 — Trade universes: ownership and target model

**DECIDED 2026-07-16.** Universes are named ticker sets (possibly industries); books trade one
or multiple; performance evaluation must be able to tell which universes a book was trading at
a given time, and cross-universe comparisons should be identifiable. Decisions:

- **Definitions stay file-backed** (`TRADE_UNIVERSES_DIR/<name>.txt`); universes may still
  change shape. Promoting them to DB entities with membership snapshots is explicitly deferred
  until universes stabilize ("membership drift" is a known, accepted gap for now).
- **`books.trade_universes` (JSON name list) is the only config home and becomes NOT NULL** —
  books are always explicitly set; account defaults are not wanted. Backfill books that rely on
  fallback today via a one-time default universe file built from the current global list.
- **`accounts.trade_universes` is dropped**; the runtime fallback chain (book → account →
  global, `_resolve_account_universe` in `src/trading/services/auto_trading/runtime.py`)
  collapses to book-only.
- **Add `book_universe_history`** — append-only (`book_id` FK, `universes_json`,
  `effective_from`, `effective_to`), written wherever book universes are set or changed,
  mirroring the `book_strategy_assignments` idiom. Answers "which universes at that time" from
  day one; lands in the same branch as the drop (work item A7).

### OD3 — Fate of `accounts.strategy`

**DECIDED 2026-07-16: remove.** Strategy truth is `strategies` + `book_strategy_assignments`.
Verified readers are display-only: `active_strategy_for_account(..., fallback=account.strategy)`
in `src/trading/services/reporting/presentation.py` and `src/trading/services/accounts/listing.py`,
plus the deletion summary in `src/trading/services/accounts/deletions.py`. A5 removes the
fallback (assignment-derived value only) alongside the column drop.

### OD4 — Broker columns: 1:1 split vs keep on `accounts`

**DECIDED 2026-07-16: keep on `accounts`.** Broker connection is core account custody metadata;
no split table. The Live Trading Safety Guard is untouched. A6 is closed as documentation-only:
note the decision in `db-schema.md` when its accounts section is next regenerated.

### OD5 — Endgame for the `trades` table

**DECIDED 2026-07-16: retire `trades`** — no duplicated information; `orders`/`order_fills`
handle the data more completely. Move all readers, delete the bridge, drop the table (work
item B1). Context: every book fill currently writes both an `orders`/`order_fills` row
(book-keyed, authoritative) and a `trades` row via the `on_fill` bridge in
`src/trading/services/auto_trading/runtime.py` (`_bridge_to_account_ledger`) — the seam that
`src/trading/services/execution/submission.py` documents as pending accounting unification.
The `trades` readers to move:
  - `apps/paper_trading_web/backend/routes/accounts.py` — account trade list via
    `list_account_trades`
  - `src/trading/services/operational_settings/enforcement.py` — global trade throttle counts
    via `fetch_count_between`
  - CLI manual trade entry (`record_trade` in `src/trading/interfaces/cli/`)
  - runtime reconciliation (`src/trading/services/auto_trading/runtime_reconciliation.py`)

## Work Items

### Group A — Settings ownership (shrink `accounts`)

#### A1 — Drop account rotation columns

**Status: ready — no remaining readers.** `AccountRecord` no longer materializes any `rotation_*`
field (ADR 014) and no code reads them from `accounts`; rotation scheduling is book-owned and
rotation state lives in `book_strategy_assignments` and `rotation_decisions`.

- Columns: `rotation_enabled`, `rotation_mode`, `rotation_optimality_mode`,
  `rotation_interval_days`, `rotation_interval_minutes`, `rotation_lookback_days`,
  `rotation_schedule`, `rotation_regime_strategy_risk_on`, `rotation_regime_strategy_neutral`,
  `rotation_regime_strategy_risk_off`, `rotation_overlay_mode`, `rotation_overlay_min_tickers`,
  `rotation_overlay_confidence_threshold`, `rotation_overlay_watchlist`, `rotation_active_index`,
  `rotation_last_at`, `rotation_active_strategy`
- Migration: single `accounts` rebuild dropping the columns (0002 pattern). No backfill needed.
- Validation: accounts + books suites; account create/read/delete via UI backend.

#### A2 — Execution settings cutover (readers → `books` columns, backfill, drop)

**Status: unblocked (OD1 decided: fold into `books`); readers remain.** Live execution still
reads account columns:

- `src/trading/services/books/execution.py` — `risk_policy`, `stop_loss_pct`,
  `take_profit_pct`, `instrument_mode`
- `src/trading/services/auto_trading/execution.py` — `trade_size_pct`, `max_position_pct`
- `book_execution_settings` exists but is not consumed by the execution path (only the parameters
  view and catalog seeding touch it).

One atomic branch: add the execution columns to `books` (including `max_trades_per_run`),
backfill from `book_execution_settings` rows where present and account values otherwise, move
the readers to `books`, drop the `book_execution_settings` table and the account columns
(`learning_enabled`, `risk_policy`, `stop_loss_pct`, `take_profit_pct`, `profit_take_pct`,
`max_loss_pct`, `trade_size_pct`, `max_position_pct`, `instrument_mode`), and remove the fields
from `AccountRecord` plus account settings validation/UI surfaces.

- Validation: auto-trading + books execution suites; a paper-trading run producing intents from
  book settings only.

#### A3 — Option settings cutover (readers → `books` columns, backfill, drop)

**Status: unblocked (OD1 decided: fold into `books`); readers remain.** Option/leaps selection
still reads account columns:

- `src/trading/domain/auto_trading_policy.py` — strike offset, premium cap, DTE note fields
- `src/trading/services/auto_trading/execution.py` — `option_min_dte`
- `src/trading/services/reporting/presentation.py` — option settings display
- `src/trading/services/accounts/config.py` — option range validation

Same atomic shape as A2 for: `option_strike_offset_pct`, `option_min_dte`, `option_max_dte`,
`option_type`, `target_delta_min`, `target_delta_max`, `max_premium_per_trade`,
`max_contracts_per_trade`, `iv_rank_min`, `iv_rank_max`, `roll_dte_threshold`. Target home is
columns on `books` (OD1); `book_option_settings` is dropped after its values fold in. Account
profile JSON configs (`src/infrastructure/config/account_profiles/`) must move their option
blocks to the book layer in the same branch.

- Validation: auto-trading suites incl. leaps paths; reporting output for an options book.

#### A4 — Goal columns (OD2 decided: drop)

Drop `accounts.goal_min_return_pct`, `goal_max_return_pct`, `goal_period`. One branch:
rebuild `accounts` without the three columns; account create/config surfaces
(`src/trading/services/accounts/config.py`, `mutations.py`, account profile JSONs, CLI shared
handlers), the web backend account contract
(`apps/paper_trading_web/backend/account_contract/mappings.py`,
`services/accounts/summaries.py`), and `AccountRecord` shed the fields. CRUD/display readers
only — no execution path reads account goals.

`accounts.trade_universes` is handled by A7 (OD6 decided), not this item.

#### A5 — `accounts.strategy` (OD3 decided: remove)

Remove the column, the `AccountRecord.strategy` field, and the display-only fallback readers
(`reporting/presentation.py`, `accounts/listing.py`, `accounts/deletions.py` — verified the
complete list 2026-07-16). Active strategy displays derive from `book_strategy_assignments`
with no account fallback. Roadmap previously omitted this column entirely.

#### A6 — Broker settings (OD4 decided: keep on `accounts`)

**Closed — no schema change.** Broker columns stay on `accounts` as custody metadata; the Live
Trading Safety Guard is untouched. Remaining action is documentation-only (note in
`db-schema.md`).

#### A7 — Trade universes: book-only, required, historied (OD6 decided)

One atomic branch implementing OD6:

- Migration: create `book_universe_history`; create a default universe file from the current
  global ticker list if any book needs it; backfill `books.trade_universes` (account value
  where the book's is NULL, else the default universe); rebuild `books` with
  `trade_universes TEXT NOT NULL`; seed one open history row per book; rebuild `accounts`
  without `trade_universes` (can share the A4 rebuild if branched together).
- Code: `_resolve_account_universe` collapses to book-only (`src/trading/services/auto_trading/
  runtime.py`); the book-universe fallback branch in `src/trading/services/books/execution.py`
  simplifies; book create/update surfaces require universes and write history rows; account
  create/config and web contract surfaces shed the field.
- Validation: auto-trading runtime + books suites; every existing book trades the same tickers
  before and after; changing a book's universes closes the old history row and opens a new one.

### Group B — Trade history unification

#### B1 — Retire the fill→trades bridge (OD5 decided: retire `trades`)

Move the four reader surfaces listed in OD5 to
`orders`/`order_fills` (+ `ledger` for cash effects), delete `_bridge_to_account_ledger` and the
`on_fill` seam, convert CLI manual trade entry to create an order + fill (or a ledger adjustment),
then drop `trades` in a numbered migration. This removes the last account-keyed execution history
and makes book-level and account-level P&L derive from one source.

- Validation: accounting, auto-trading runtime, operational-settings (throttle), and web backend
  accounts-route suites; reconciliation run against a live-shaped DB copy.

#### B2 — Interim `trades` fixes (only if B1 is deferred)

If `trades` must live longer: add `book_id` (nullable, FK to books) so book attribution isn't
parsed out of the `note` field, and add the missing `trades(account_id)` index (SQLite does not
auto-index FK columns; account cascade deletes and per-account queries currently scan). Skip
entirely if B1 lands first.

### Group C — Referential integrity

#### C1 — `promotion_reviews.strategy_name` → FK + snapshot

`promotion_reviews` stores only a strategy name string; renaming a strategy key detaches history.
Apply the same pattern the table already uses for accounts (`account_id` + `account_name_snapshot`):
add `strategy_id INTEGER REFERENCES strategies(id)` populated by matching `strategy_key`, keep
the existing name column as the snapshot. Rows whose names no longer resolve keep a NULL id.

- Migration: `ALTER TABLE ADD COLUMN` + backfill UPDATE (no rebuild needed).
- Validation: promotion suites; promotion review UI list/detail.

#### C2 — FK index audit

Verified 2026-07-16: `trades(account_id)` is the only unindexed FK used by cascades or hot
queries (covered by B1/B2). Re-run the audit after each table rebuild; every FK column referenced
by a cascade delete or a routine filter should be covered by some index prefix.

### Group D — Hygiene and documentation-only items

#### D1 — Document derived caches on `positions`

`positions.market_value` and `unrealized_pnl` are price-dependent caches next to authoritative
`qty`/`avg_cost`; they are only as fresh as the last mark. Add a note to `db-schema.md` so
consumers don't treat them as truth.

#### D2 — Money-as-REAL known limitation + cash invariant check

Cash, qty, and price are floats throughout. Acceptable for paper trading; do **not** churn the
schema. Instead: (a) record the limitation in `db-schema.md`; (b) add a small invariant check
(script or existing checks profile) asserting `books.current_cash` reconciles with the `ledger`
sum within a tolerance, so float drift surfaces as a report instead of a silent divergence.

#### D3 — `global_settings` growth watch

The single-row pattern (`id = 1` CHECK) is fine. Note in `db-schema.md` that it intentionally
mixes runtime throttles, evaluation weights, and promotion gates, and revisit a split only if a
fourth domain lands there.

#### D4 — Schema doc + diagram regeneration discipline

After every group above: regenerate the diagram viewer, sync `db-schema.md`, and run
`python -m scripts.checks.docs.readme_check`. (Standing rule, restated here so each branch's
definition-of-done includes it.)

## Completed

- **FK cascade rebuilds** (`features/database-accounts-split`): migration `0002` rebuilt
  `rotation_decisions` to full CASCADE; account-deletion cascade covered by tests; admin deletions
  back up the database by default. Remaining: run `alembic upgrade` on the live database —
  `ensure_db()` refuses to start on a stale revision, so this cannot silently drift.
- **Sleeve retirement and book-rotation cutover**: no sleeve code remains in `src/`; the
  book-rotation cutover has run everywhere.

## Suggested Order

Proposed sequencing — to be reviewed before implementation starts:

1. **A1** (rotation column drop) — ready now, lowest risk, proves the accounts-rebuild pattern.
2. ~~Decide ODs~~ **All six decided 2026-07-16** (OD1 fold into books; OD2/OD3 drop; OD4 keep
   broker on accounts; OD5 retire trades; OD6 universes book-only + required + historied).
3. **A2 then A3** (execution, option cutovers into `books`) — closes the dual-ownership window
   on live execution, the highest-risk open state.
4. **B1** (retire `trades` for `orders`/`order_fills`) — biggest correctness payoff after
   settings are single-homed.
5. **C1** (promotion strategy FK) — independent, can slot anywhere.
6. **A4, A5** (goal columns, `accounts.strategy`) — small rebuilds.
7. **A7** (trade universes: required + historied) — pairs naturally with A4.
8. **D1–D3** — documentation items (including the A6 broker "keep" note), can ride along with
   any branch touching the same docs.

One ownership group per branch; each branch is reader-move + backfill + drop, atomically.

## Boundaries

- Do not introduce generic EAV/category/value tables for account or book settings.
- Do not add mapping tables unless the relationship is genuinely many-to-many or historical.
- Do not remove legacy columns until the same branch moves every reader and the migration
  backfills the new home.
- Do not weaken the live-trading safety guard while moving broker settings.
- Keep account-level history and retention decisions separate from settings cleanup. Promotion,
  risk, backtest, and walk-forward retention still need explicit product/operator decisions.
- Physical schema changes go through numbered Alembic migrations only (ADR 015); every rebuild
  follows the `0002` pattern with a reversible downgrade.

## Related Docs

- [Database Schema Reference](db-schema.md)
- [DB Migration System](db-migration-system.md)
