---
name: sqlite-table-rebuild
description: Shows the migration pattern required when SQLite schema changes need table rebuilds, such as changing foreign-key ON DELETE actions.
---

# SQLite Table Rebuild Migration

Use this reference when a schema change cannot be expressed as `ALTER TABLE ... ADD COLUMN`.
Changing a foreign-key `ON DELETE` action is the main case for account-deletion cascade work.

## When This Applies

- Changing `ON DELETE` or `ON UPDATE` behavior.
- Adding, changing, or removing a table constraint.
- Changing primary keys, unique constraints, or check constraints.
- Renaming or dropping columns, only after an explicit human decision and backup plan.

## Required Shape

1. Update fresh DDL in `src/infrastructure/database/schema.py`.
2. Add an idempotent migration function in `src/infrastructure/database/migrations.py` or a closely owned migration module.
3. Register it from `src/infrastructure/database/init.py` after `SCHEMA_SQL` and additive column migrations that the table depends on.
4. Wrap the rebuild in an explicit transaction.
5. Disable FK enforcement only for the rebuild window if SQLite requires it, then re-enable it.
6. Copy rows into the replacement table using an explicit column list.
7. Recreate indexes and unique constraints.
8. Run `PRAGMA foreign_key_check` and fail if any violations remain.
9. Add tests for fresh schema and migrated legacy schema.

## Example: Add Cascade To `order_fills.order_id`

This is illustrative. Keep names, columns, indexes, and guards aligned with the actual table shape at implementation time.

```python
def _order_fills_has_order_cascade(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA foreign_key_list(order_fills)").fetchall()
    return any(
        row["from"] == "order_id"
        and row["table"] == "orders"
        and row["on_delete"].upper() == "CASCADE"
        for row in rows
    )


def ensure_order_fills_order_delete_cascade(conn: sqlite3.Connection) -> None:
    if _order_fills_has_order_cascade(conn):
        return

    conn.execute("BEGIN")
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE order_fills_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                broker_fill_id TEXT,
                exec_id TEXT,
                filled_qty REAL NOT NULL,
                fill_price REAL NOT NULL,
                commission REAL NOT NULL DEFAULT 0,
                fill_time TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                UNIQUE (order_id, exec_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO order_fills_new (
                id, order_id, broker_fill_id, exec_id, filled_qty,
                fill_price, commission, fill_time
            )
            SELECT
                id, order_id, broker_fill_id, exec_id, filled_qty,
                fill_price, commission, fill_time
            FROM order_fills
            """
        )
        conn.execute("DROP TABLE order_fills")
        conn.execute("ALTER TABLE order_fills_new RENAME TO order_fills")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_order_fills_order_id ON order_fills(order_id)")
        conn.execute("PRAGMA foreign_keys = ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign-key violations after order_fills rebuild: {violations!r}")
    except Exception:
        conn.rollback()
        conn.execute("PRAGMA foreign_keys = ON")
        raise
    else:
        conn.commit()
```

## Safety Checklist

- The migration is idempotent and skips when the target FK action already exists.
- The fresh DDL and migrated DDL produce the same `PRAGMA foreign_key_list(<table>)` result.
- The copied column list is explicit; no `SELECT *`.
- Every index from the old table is recreated.
- Any `DROP TABLE` or table rename is called out in review with a backup requirement.
- Tests cover pre-migration legacy data, migration idempotency, and `PRAGMA foreign_key_check`.

## Validation Commands

```sh
.venv/Scripts/python.exe -m scripts.data_ops.audit_foreign_keys --scope all
.venv/Scripts/pytest.exe tests/src/infrastructure/database -k "schema or migration" --no-cov
```

