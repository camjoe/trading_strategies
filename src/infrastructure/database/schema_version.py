"""Expected Alembic head revision, readable without importing Alembic.

Alembic and SQLAlchemy are deliberately ops-only dependencies
(docs/adr/015-numbered-alembic-migrations.md): runtime code learns the expected
head from this constant and reads the database's recorded revision with plain
SQL, so the application import graph never touches the migration tooling. A
repository check enforces that the constant matches the migration directory's
single head.
"""

from __future__ import annotations

from typing import Any

# The single head revision of src/infrastructure/database/alembic/versions/.
# Update this in the same commit that adds a new migration revision.
EXPECTED_HEAD_REVISION = "0013"

# Table Alembic uses to record the applied revision.
ALEMBIC_VERSION_TABLE = "alembic_version"


def read_database_revisions(conn: Any) -> tuple[str, ...]:
    """Return the revision rows recorded in the database.

    Empty when the database is unversioned (no ``alembic_version`` table or no
    rows); more than one entry means a branched history, which callers must
    treat as an error state.
    """
    table_row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (ALEMBIC_VERSION_TABLE,),
    ).fetchone()
    if table_row is None:
        return ()
    rows = conn.execute(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}").fetchall()
    return tuple(str(row[0]) for row in rows)
