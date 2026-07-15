"""One-time reconciliation of a pre-Alembic database to the revision ``0001`` schema.

TRANSITIONAL — delete this module (and its test) once every deployed database has crossed over to
Alembic (`docs/pending-deploy-steps.md` Step 1). The retired probe system never dropped tables or
columns from existing databases, so live databases carry probe-era leftovers that revision
``0001`` (the current clean schema) does not have: the superseded ``broker_orders`` and
sleeve/rotation-episode tables, plus the retired ``strategy_param_sets`` store and the unused
``book_strategy_assignments.param_set_id`` column. A database that still carries these cannot
baseline (or pass ``verify``) against ``0001``.

This backs the database up, then drops the leftovers and rebuilds ``book_strategy_assignments`` to
the clean shape (a plain ``DROP COLUMN param_set_id`` fails when the legacy foreign key is present,
which some databases carry and some do not, so the rebuild is used uniformly). It stops before
baselining; run ``manage_db_migrations baseline`` + ``verify`` afterward.

Run::

    python -m scripts.data_ops.reconcile_to_0001
"""

from __future__ import annotations

import argparse
import sqlite3

from infrastructure.database.backend import SQLiteBackend, get_backend
from infrastructure.database.schema_version import read_database_revisions
from trading.interfaces.runtime.data_ops.admin import backup_database

_PREFIX = "[reconcile-to-0001]"

# Probe-era tables that revision 0001 does not define. Dropped if present.
# strategy_param_sets is dropped after the book_strategy_assignments rebuild, once nothing
# references it.
_ORPHAN_TABLES = (
    "broker_orders",
    "sleeve_orders",
    "sleeve_fills",
    "sleeve_positions",
    "sleeve_ledger",
    "rotation_episodes",
)

# book_strategy_assignments rebuilt to the clean 0001 shape — drops the legacy param_set_id column
# and its foreign key. Executed statement-by-statement (not executescript) to stay inside one
# explicit transaction.
_REBUILD_STATEMENTS = (
    """
    CREATE TABLE book_strategy_assignments_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        strategy_id INTEGER NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        is_incumbent INTEGER NOT NULL DEFAULT 1 CHECK (is_incumbent IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id)
    )
    """,
    """
    INSERT INTO book_strategy_assignments_new
        (id, book_id, strategy_id, effective_from, effective_to, is_incumbent, created_at, updated_at)
        SELECT id, book_id, strategy_id, effective_from, effective_to, is_incumbent, created_at, updated_at
        FROM book_strategy_assignments
    """,
    "DROP TABLE book_strategy_assignments",
    "ALTER TABLE book_strategy_assignments_new RENAME TO book_strategy_assignments",
    (
        "CREATE UNIQUE INDEX idx_book_assignments_open_per_book "
        "ON book_strategy_assignments(book_id) WHERE effective_to IS NULL"
    ),
    "CREATE INDEX idx_book_assignments_book_effective ON book_strategy_assignments(book_id, effective_from DESC)",
    (
        "CREATE INDEX idx_book_assignments_strategy_effective "
        "ON book_strategy_assignments(strategy_id, effective_from DESC)"
    ),
)


def _present_tables(conn: sqlite3.Connection, names: tuple[str, ...]) -> list[str]:
    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return [name for name in names if name in existing]


def _apply(conn: sqlite3.Connection) -> None:
    """Drop leftovers and rebuild book_strategy_assignments in one transaction.

    Foreign-key enforcement is disabled for the rebuild window (a no-op inside an open
    transaction, so it brackets an explicit BEGIN), and a violation check runs before commit.
    """
    conn.isolation_level = None  # manual transaction control
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        try:
            for table in _ORPHAN_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
            for statement in _REBUILD_STATEMENTS:
                conn.execute(statement)
            conn.execute("DROP TABLE IF EXISTS strategy_param_sets")
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Foreign-key violations after reconciliation: {violations!r}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def run_reconcile() -> int:
    """Back up and reconcile the configured database to the ``0001`` schema."""
    backend = get_backend()
    if not isinstance(backend, SQLiteBackend):
        print(f"{_PREFIX} Only SQLite backends are supported.")
        return 1
    path = backend.db_path
    print(f"{_PREFIX} Database: {path}")
    if not path.exists():
        print(f"{_PREFIX} Refusing: database does not exist — nothing to reconcile.")
        return 1

    probe = sqlite3.connect(path)
    try:
        if read_database_revisions(probe):
            print(
                f"{_PREFIX} Refusing: database is already Alembic-versioned. Reconciliation is a "
                "pre-baseline step for unversioned databases only."
            )
            return 1
        dropped = _present_tables(probe, _ORPHAN_TABLES + ("strategy_param_sets",))
    finally:
        probe.close()

    backup_path = backup_database()
    print(f"{_PREFIX} Backup created: {backup_path}")

    conn = backend.open_connection()
    try:
        _apply(conn)
    finally:
        conn.close()

    print(f"{_PREFIX} Dropped leftover tables: {', '.join(dropped) if dropped else '(none present)'}.")
    print(f"{_PREFIX} Rebuilt book_strategy_assignments to the clean 0001 shape.")
    print(f"{_PREFIX} Next: 'python -m scripts.data_ops.manage_db_migrations baseline' then 'verify'.")
    return 0


def main() -> int:
    argparse.ArgumentParser(
        description="One-time: reconcile a pre-Alembic database to the revision 0001 schema (backs up first).",
    ).parse_args()
    return run_reconcile()


if __name__ == "__main__":
    raise SystemExit(main())
