"""Create the configured database schema from the Alembic revision chain.

Fresh-setup operator command (docs/numbered-database-migration-plan.md):

- Creates a missing or empty configured database and applies revisions from
  base through ``head``.
- Refuses a populated, unversioned database — baseline it instead via
  ``python -m scripts.data_ops.manage_db_migrations baseline``.
- Refuses an already-versioned database — inspect and upgrade it via
  ``python -m scripts.data_ops.manage_db_migrations``.
- Never seeds application data.

Run::

    python -m scripts.data_ops.setup_db_schema
"""

from __future__ import annotations

import argparse
from typing import Any

from infrastructure.database import migration_runner
from infrastructure.database.backend import get_backend
from infrastructure.database.schema_version import ALEMBIC_VERSION_TABLE, read_database_revisions


def _application_table_count(conn: Any) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != ?",
        (ALEMBIC_VERSION_TABLE,),
    ).fetchone()
    return int(row[0])


def run_setup() -> int:
    """Apply base→head to the configured database if it is missing or empty."""
    backend = get_backend()
    db_path = getattr(backend, "db_path", None)
    if db_path is not None:
        print(f"[setup-db-schema] Database: {db_path}")

    conn = backend.open_connection()
    try:
        revisions = read_database_revisions(conn)
        if revisions:
            print(
                f"[setup-db-schema] Refusing: database is already versioned at {', '.join(revisions)}. "
                "Use 'python -m scripts.data_ops.manage_db_migrations status' to inspect it "
                "and 'upgrade' to bring it to head."
            )
            return 1
        if _application_table_count(conn) > 0:
            print(
                "[setup-db-schema] Refusing: database already contains tables but has no Alembic "
                "revision. Baseline it instead: "
                "'python -m scripts.data_ops.manage_db_migrations baseline'."
            )
            return 1

        migration_runner.upgrade("head", connection=conn)
        applied = read_database_revisions(conn)
        print(f"[setup-db-schema] Created schema at revision {', '.join(applied)}.")
        print("[setup-db-schema] No application data was seeded (seeding is a separate command).")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create the configured database schema by applying Alembic revisions base->head. "
            "Refuses populated or already-versioned databases; never seeds data."
        ),
    )
    parser.parse_args()
    return run_setup()


if __name__ == "__main__":
    raise SystemExit(main())
