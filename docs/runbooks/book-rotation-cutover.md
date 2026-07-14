# Runbook: Book-Rotation Cutover (one-time)

Type: runbook
Status: Active — delete this runbook (and the data-op module) once every existing DB has been migrated
Created: 2026-07-10
Last Reviewed: 2026-07-13
Purpose: The one-time operator procedure that moves rotation scheduling ownership from the retained
account columns onto `book_rotation_settings` and opens default-book assignments after the
execution-mode-collapse branch deploys.
Related: [Runtime Operations](runtime-operations.md), [Production Runtime Host](production-runtime-host.md),
[ADR 014 — Execution-Mode Collapse](../adr/014-execution-mode-collapse.md)

## Why this exists

The execution-mode collapse (ADR 014) made books the only execution path: the runtime trades every
active, openly assigned book — the default book included — and rotation is gated by each book's own
`book_rotation_settings` row (`rotation_enabled`, `rotation_schedule`, `rotation_lookback_days`).
The account rotation columns are retained on the table but **no longer read by anything**.

An existing database must be cut over **once, explicitly**, because:

- **Default books may have no open assignment.** Former account-mode accounts traded the default
  book with the account's strategy column; post-collapse an unassigned book simply doesn't trade
  (fail-safe: nothing errors, nothing trades).
- **Books may have no scheduling row, or a stale copy.** The book-owned `rotation_enabled` gate
  defaults to **off**, so a book without a synced row silently stops being rotation-evaluated.
  The account columns were the live source of truth until this branch; seeded copies may be stale.

Fresh databases need **nothing** — accounts created post-collapse get their assignment at creation
and their book scheduling from profiles / the admin API.

## What the data-op does

`python -m trading.interfaces.runtime.data_ops.migrate_book_rotation`

For every account it:

1. **Ensures the default book exists** (bootstrapped from the account row).
2. **Re-syncs rotation scheduling onto every book of the account** — `rotation_enabled`,
   `rotation_schedule`, `rotation_lookback_days` copied from the retained account columns;
   policy columns (weights, threshold, cooldown, min-trades) are preserved.
3. **Opens the default book's assignment where missing**, resolved the way the retired account
   flow did (`rotation_active_strategy` if in the schedule → schedule at the active index → base
   `strategy`), creating a draft `strategies` row for labels the catalog doesn't know yet. A book
   with an open assignment is never overwritten.

It is **idempotent**: re-running it is safe. It prints a summary
(`scheduling rows synced=N assignments opened=M`).

## Procedure

Run on the host, from the repo root, with the venv interpreter, **while the scheduler jobs are not
mid-run** (any time outside the daily run window is fine). Windows hosts use
`.venv\Scripts\python.exe` in place of `.venv/bin/python`.

### 1. Back up

```bash
.venv/bin/python -m trading.interfaces.runtime.data_ops.admin backup-db   # or copy local/paper_trading.db
ls local/db_backups/   # confirm a fresh snapshot exists
```

### 2. Run the data-op

```bash
.venv/bin/python -m trading.interfaces.runtime.data_ops.migrate_book_rotation
```

### 3. Verify

Both queries must return **zero rows**:

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

Spot-check the effective values through the CLI:

```bash
.venv/bin/python -m trading.interfaces.cli.main parameters
```

Each book's rotation group should show the expected `rotation_enabled` / `rotation_schedule` /
`rotation_lookback_days` with source `db`.

### 4. Confirm the runtime

After the next daily run (or a manually triggered one), confirm default books traded where
expected, rotation decisions appear only for rotation-enabled books, and `risk_snapshots` rows are
written for the formerly account-mode accounts.

### 5. Cleanup (after every environment is migrated)

Delete `src/trading/interfaces/runtime/data_ops/migrate_book_rotation.py`, its test, and this
runbook; remove Step 2 from `docs/pending-deploy-steps.md`.

## Rollback

Restore the pre-migration snapshot from `local/db_backups/` and re-run from step 2. The op only
adds/updates `book_rotation_settings` rows and opens assignments — it deletes nothing.
