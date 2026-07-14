"""Programmatic runner for the repository-owned Alembic environment.

Ops-only module: it imports Alembic and SQLAlchemy, which are dev/ops
dependencies (docs/numbered-database-migration-plan.md). Application runtime
must not import this module — ``ensure_db()`` checks the database revision
with plain SQL against ``schema_version.EXPECTED_HEAD_REVISION``.

Every command runs against a live DBAPI connection opened from the active
``DatabaseBackend`` (or an explicitly supplied one), never a URL, so
``set_backend()`` test injection and in-memory databases work unchanged.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from infrastructure.database.backend import get_backend

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


def build_config() -> Config:
    """Return the Alembic config for the repository-owned environment."""
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    # Revisions are hand-authored with explicit numeric ``--rev-id`` values;
    # this template keeps generated filenames aligned with that numbering.
    config.set_main_option("file_template", "%%(rev)s_%%(slug)s")
    return config


def repository_head() -> str:
    """Return the migration directory's single head revision.

    Raises ``RuntimeError`` when the directory has zero or multiple heads —
    the revision chain must stay linear.
    """
    heads = ScriptDirectory.from_config(build_config()).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Migration directory must have exactly one head; found {list(heads)!r}")
    return heads[0]


@contextmanager
def _connected_config(connection: sqlite3.Connection | None) -> Iterator[Config]:
    """Yield a Config whose ``connection`` attribute wraps a live connection.

    Opens (and then closes) a connection from the active backend when none is
    supplied; a caller-supplied connection is left open, and its pending
    transaction state is preserved around the SQLAlchemy wrapper.
    """
    owns_connection = connection is None
    raw = get_backend().open_connection() if connection is None else connection
    engine = create_engine("sqlite://", creator=lambda: raw, poolclass=StaticPool)
    try:
        with engine.begin() as wrapped:
            config = build_config()
            config.attributes["connection"] = wrapped
            yield config
    finally:
        # close=False: the engine must not close the DBAPI connection it
        # borrowed — the caller (or the owns_connection branch) owns it.
        engine.dispose(close=False)
        if owns_connection:
            raw.close()


def upgrade(revision: str = "head", *, connection: sqlite3.Connection | None = None) -> None:
    """Apply revisions up to *revision* (default: head)."""
    with _connected_config(connection) as config:
        command.upgrade(config, revision)


def downgrade(revision: str, *, connection: sqlite3.Connection | None = None) -> None:
    """Revert revisions down to *revision*. The target is always explicit."""
    with _connected_config(connection) as config:
        command.downgrade(config, revision)


def stamp(revision: str, *, connection: sqlite3.Connection | None = None) -> None:
    """Record *revision* in ``alembic_version`` without running any DDL."""
    with _connected_config(connection) as config:
        command.stamp(config, revision)
