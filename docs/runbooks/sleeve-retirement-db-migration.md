# Runbook: Sleeve-Retirement DB Migration (one-time)

Type: runbook
Status: Active — delete this runbook (and the data-op module) once every existing DB has been migrated
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: The one-time operator procedure that migrates an existing database off the legacy sleeve
tables after the sleeve-retirement branch deploys — run the data-op, verify, drop the orphaned
tables, then delete the migration tooling.
Related: [Runtime Operations](runtime-operations.md), [Production Runtime Host](production-runtime-host.md),
[ADR 010 — Book-Keyed Execution Model](../adr/010-book-keyed-execution-model.md)

## Why this exists

The sleeve retirement (branch `features/sleeve-retirement`) removed the sleeve
concept: **books** + `book_strategy_assignments` are now the only store for which strategy units an
account runs. During the transition the runtime *self-migrated* legacy data lazily (copying each
sleeve's config onto its book at first read). That lazy machinery was later deleted,
so the deployed code **no longer reads the legacy tables at all** — an existing database must be
migrated **once, explicitly**, or any sleeve configuration that was never mirrored simply won't
trade (fail-safe: unassigned books are skipped; nothing errors, but nothing trades on them either).

Fresh databases need **nothing** — the current schema no longer creates the legacy tables, and
the data-op detects that and exits as a no-op.

## What the data-op does

`python -m trading.interfaces.runtime.data_ops.migrate_sleeve_books`

For every row still in the legacy `strategy_sleeves` table it:

1. **Ensures the book exists** — a non-default book with the same account + name, seeded with the
   sleeve's balances if the book has to be created (books already created by earlier runs are left
   untouched — book state is authoritative).
2. **Mirrors status and universes** — sleeve `active`/`paused`/`retired` → book
   `active`/`paused`/`closed`; `trade_universes` copied across.
3. **Copies the open strategy assignment** — the sleeve's incumbent strategy (and its pinned
   `param_set_id`) becomes the book's open row in `book_strategy_assignments`, but **only when the
   book has no open assignment yet**. A book the rotation path has already written to is never
   overwritten.

It is **idempotent**: re-running it is safe and changes nothing after the first successful pass.
It prints a summary (`bridging books created: N` / `assignments copied: M`).

## Procedure

Run on the host, from the repo root, with the venv interpreter, **while the scheduler jobs are not
mid-run** (any time outside the daily run window is fine).

### 1. Back up

```bash
.venv/bin/python -m trading.interfaces.runtime.data_ops.admin backup   # or copy local/paper_trading.db
ls local/db_backups/   # confirm a fresh snapshot exists
```

### 2. Run the migration

```bash
.venv/bin/python -m trading.interfaces.runtime.data_ops.migrate_sleeve_books
```

Expected output: the created/copied counts. Zeros are fine — it means everything was already
mirrored by the earlier lazy migration during normal runs.

### 3. Verify

Every active legacy sleeve should now have a matching active book with an open assignment:

```sql
-- Should return no rows: active sleeves whose book is missing an open assignment
SELECT s.account_id, s.name
FROM strategy_sleeves s
JOIN books b ON b.account_id = s.account_id AND b.name = s.name
LEFT JOIN book_strategy_assignments a ON a.book_id = b.id AND a.effective_to IS NULL
WHERE s.status = 'active'
  AND EXISTS (SELECT 1 FROM sleeve_strategy_assignments sa
              WHERE sa.sleeve_id = s.id AND sa.effective_to IS NULL)
  AND a.id IS NULL;
```

### 4. Drop the orphaned tables (explicit sign-off)

Nothing in the code reads or writes these four tables anymore; fresh DBs never create them.

```sql
DROP TABLE IF EXISTS sleeve_strategy_assignments;
DROP TABLE IF EXISTS strategy_sleeves;
DROP TABLE IF EXISTS sleeve_risk_decisions;
DROP TABLE IF EXISTS portfolio_risk_snapshots;
```

### 5. Confirm the runtime is healthy

Run (or wait for) the next daily job and check that the expected books traded / were evaluated —
the monitor's "Strategy Books" panel and the daily report's `book_performance` section are the
quickest checks.

### 6. Delete the migration tooling

Once **every** environment's DB has been migrated and dropped, remove the now-dead tooling in a
small cleanup commit:

- `src/trading/interfaces/runtime/data_ops/migrate_sleeve_books.py`
- this runbook (`docs/runbooks/sleeve-retirement-db-migration.md`)
- the corresponding rows in `docs/runbooks/README.md` and `docs/maps/trading-package-map.md`,
  and Step 1 in `docs/pending-deploy-steps.md`

## Rollback

If anything looks wrong after step 4, restore the pre-migration snapshot from `local/db_backups/`
and re-run from step 2. Before step 4 no destructive change has occurred — the data-op only adds
book rows/assignments and never deletes or overwrites existing book state.
