# Pending One-Time DB Steps

Type: notes
Status: Active
Created: 2026-07-12
Last Reviewed: 2026-07-12
Purpose: Single tracker for the pending one-time database steps — what still needs to run against an
existing database (and what still needs building) so no loose end is forgotten.
Related: [Overview](overview.md), [Sleeve-Retirement DB Migration](runbooks/sleeve-retirement-db-migration.md),
[Book-Rotation Cutover](runbooks/book-rotation-cutover.md), [ADR 014](adr/014-execution-mode-collapse.md)

> Consolidated tracker; the full per-step procedures live in the linked runbooks.
>
> - **Steps 1 & 2 are code-complete** — nothing to build. Each needs **one operator action** against
>   an *existing* database; **fresh databases need nothing** (the data-ops detect this and no-op).
> - **Step 3 is NOT built yet** — it's a follow-up branch (schema/code cleanup + a new data-op) to
>   write after the strategy-catalog work merges. Listed here so the loose end isn't forgotten.
>
> Windows: use `.venv\Scripts\python.exe` in place of `.venv/bin/python` below.
> Run any data-op **while the scheduler jobs are not mid-run** (any time outside the daily run window).

---

## Step 1 — Sleeve-Retirement DB Migration

**When:** the `features/sleeve-retirement` branch deploys to a host with an existing DB.

**Why:** the sleeve concept was removed; books + book strategy assignments are now the only store
for what an account runs. The deployed code no longer reads the legacy sleeve tables, so an existing
DB must be migrated once explicitly — otherwise any sleeve config that was never mirrored simply
won't trade (fail-safe: unassigned books are skipped, nothing errors).

**Procedure:**

1. **Back up** the DB:
   ```
   .venv/bin/python -m trading.interfaces.runtime.data_ops.admin backup
   ls local/db_backups/   # confirm a fresh snapshot
   ```
2. **Run the migration** (idempotent; prints created/copied counts, zeros are fine):
   ```
   .venv/bin/python -m trading.interfaces.runtime.data_ops.migrate_sleeve_books
   ```
3. **Verify** — this query should return **no rows** (active sleeves whose book lacks an open
   assignment):
   ```sql
   SELECT s.account_id, s.name
   FROM strategy_sleeves s
   JOIN books b ON b.account_id = s.account_id AND b.name = s.name
   LEFT JOIN book_strategy_assignments a ON a.book_id = b.id AND a.effective_to IS NULL
   WHERE s.status = 'active'
     AND EXISTS (SELECT 1 FROM sleeve_strategy_assignments sa
                 WHERE sa.sleeve_id = s.id AND sa.effective_to IS NULL)
     AND a.id IS NULL;
   ```
4. **Drop the four orphaned tables** (explicit sign-off — nothing reads them anymore):
   ```sql
   DROP TABLE IF EXISTS sleeve_strategy_assignments;
   DROP TABLE IF EXISTS strategy_sleeves;
   DROP TABLE IF EXISTS sleeve_risk_decisions;
   DROP TABLE IF EXISTS portfolio_risk_snapshots;
   ```
5. **Confirm runtime healthy** — after the next daily job, check the expected books traded /
   were evaluated (monitor "Strategy Books" panel; daily report `book_performance`).
6. **Delete the tooling** once *every* environment is migrated: the `migrate_sleeve_books.py`
   data-op, its runbook, and the related doc rows.

**Rollback:** before step 4 nothing destructive has happened (the op only adds book rows/assignments).
If anything looks wrong, restore the snapshot from `local/db_backups/` and re-run from step 2.

Full repo runbook: `docs/runbooks/sleeve-retirement-db-migration.md`

---

## Step 2 — Book-Rotation Cutover

**When:** the `features/book-owned-rotation-scheduling` branch (execution-mode collapse, ADR 014)
deploys to a host with an existing DB.

**Why:** books became the only execution path; rotation is now gated by each book's own
`book_rotation_settings` row, and the account rotation columns are no longer read. An existing DB
must be cut over once because (a) default books may have no open assignment (unassigned = doesn't
trade), and (b) books may have no scheduling row or a stale one, and the book-owned `rotation_enabled`
gate defaults to **off** — so a book without a synced row silently stops being rotation-evaluated.

**Procedure:**

1. **Back up** the DB:
   ```
   .venv/bin/python -m trading.interfaces.runtime.data_ops.admin backup
   ls local/db_backups/
   ```
2. **Run the data-op** (idempotent; prints `scheduling rows synced=N assignments opened=M`):
   ```
   .venv/bin/python -m trading.interfaces.runtime.data_ops.migrate_book_rotation
   ```
3. **Verify** — both queries must return **zero rows**:
   ```sql
   -- Default books still missing an open assignment (nothing would trade on them):
   SELECT a.name FROM accounts a
   JOIN books b ON b.account_id = a.id AND b.is_default = 1
   LEFT JOIN book_strategy_assignments s ON s.book_id = b.id AND s.effective_to IS NULL
   WHERE s.id IS NULL;

   -- Active, openly assigned books missing a rotation-settings row (rotation silently off):
   SELECT b.id, b.name FROM books b
   JOIN book_strategy_assignments s ON s.book_id = b.id AND s.effective_to IS NULL
   LEFT JOIN book_rotation_settings r ON r.book_id = b.id
   WHERE b.status = 'active' AND r.book_id IS NULL;
   ```
   Spot-check effective values via the CLI (`rotation_enabled` / `rotation_schedule` /
   `rotation_lookback_days` should show source `db`):
   ```
   .venv/bin/python -m trading.interfaces.cli.main parameters
   ```
4. **Confirm runtime** — after the next daily run, confirm default books traded where expected,
   rotation decisions appear only for rotation-enabled books, and risk snapshots are written for the
   formerly account-mode accounts.
5. **Cleanup** once *every* environment is migrated: delete the `migrate_book_rotation.py` data-op,
   its test, and the runbook.

**Rollback:** restore the snapshot from `local/db_backups/` and re-run from step 2 — the op only
adds/updates rotation-settings rows and opens assignments; it deletes nothing.

Full repo runbook: `docs/runbooks/book-rotation-cutover.md`

---

## Step 3 — Drop the legacy `strategy_param_sets` store (NOT built yet)

**When:** any time after the strategy-catalog work (`features/strategy-catalog-canonical`) merges.
Not urgent — the leftovers are inert.

**Why:** the strategy-catalog work retired the param-set thread in code (a strategy row is its own
parameterization now), but deliberately left the physical schema in place so existing DBs still match
the DDL:

- the `strategy_param_sets` table (+ its `idx_strategy_param_sets_strategy_active` index), and
- the `book_strategy_assignments.param_set_id` column (+ its FK to `strategy_param_sets`).

Both are unused and always NULL. This step removes them for good.

**This is a follow-up branch, not a ready-to-run command.** Two parts:

1. **Code cleanup** (so fresh DBs stop creating the leftovers):
   - `src/infrastructure/database/schema.py` — delete `STRATEGY_PARAM_SETS_TABLE_SQL` +
     `STRATEGY_PARAM_SETS_INDEXES_SQL` (and their entries in `SCHEMA_SQL`); drop the `param_set_id`
     column line and its `FOREIGN KEY (param_set_id) REFERENCES strategy_param_sets(id)` from
     `BOOK_STRATEGY_ASSIGNMENTS_TABLE_SQL`.
   - `src/infrastructure/database/migrations.py` — remove the `"strategy_param_sets": ()` entry in
     `TABLE_MIGRATIONS_BY_TABLE` and the `param_set_id` `ColumnMigration` in
     `BOOK_MIGRATIONS_BY_TABLE["book_strategy_assignments"]`.
   - Then `run suite` + `run checks quick` to confirm nothing referenced them.

2. **Data-op** (to drop them from existing DBs — write a small one-time module like the others):
   ```sql
   -- SQLite 3.35+ supports DROP COLUMN; the column carries a FK, so drop it before the table.
   ALTER TABLE book_strategy_assignments DROP COLUMN param_set_id;
   DROP INDEX IF EXISTS idx_strategy_param_sets_strategy_active;
   DROP TABLE IF EXISTS strategy_param_sets;
   ```
   Back up first (`data_ops.admin backup`); make it idempotent (no-op when the column/table are
   already gone, so fresh DBs need nothing).

**Verify:** `PRAGMA table_info(book_strategy_assignments);` shows no `param_set_id`; the
`strategy_param_sets` table no longer exists. A daily run still trades/rotates normally.

**Rollback:** restore the pre-op snapshot from `local/db_backups/`.

**Note:** the `docs/reference/db-schema.md` row for `strategy_param_sets` should be removed as part of
the code-cleanup commit (or regenerated via `python -m scripts.data_ops.describe_db_schema`).

**Related sleeve leftover:** once the legacy sleeve tables are dropped (Step 1), also remove the
`rotation_decisions` legacy-compat `? AS sleeve_id` synthetic column (and its explanatory comments)
in `src/trading/repositories/rotation_decisions.py`. It's an unread query alias kept only for
raw-row consumers during the transition — a pure code cleanup, no data-op needed.
