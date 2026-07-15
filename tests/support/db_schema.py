"""Build test databases at the Alembic head revision.

The migration chain is replayed once per process into a template file; every
subsequent test database is a file copy (or SQLite backup, for in-memory
connections) of that template. This keeps per-test cost flat as revisions
accumulate (docs/numbered-database-migration-plan.md, test fixture migration).
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from infrastructure.database import migration_runner

_template_path: Path | None = None


def _head_template() -> Path:
    global _template_path
    if _template_path is None:
        template = Path(tempfile.mkdtemp(prefix="trading_head_schema_")) / "head.db"
        conn = sqlite3.connect(template)
        try:
            migration_runner.upgrade("head", connection=conn)
        finally:
            conn.close()
        _template_path = template
    return _template_path


def build_db_at_head(db_path: Path) -> Path:
    """Create (or overwrite) *db_path* as an empty schema at the head revision."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_head_template(), db_path)
    return db_path


def memory_db_at_head() -> sqlite3.Connection:
    """Return an in-memory connection holding the head-revision schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    template = sqlite3.connect(_head_template())
    try:
        template.backup(conn)
    finally:
        template.close()
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
