"""Drop denormalized primitive metadata from strategies.

Revision ID: 0017
Revises: 0016

``strategies.style`` and ``strategies.required_features`` copied values that the
code ``PrimitiveSpec`` owns. Runtime never reads them: resolution keys on the
``primitive`` column and derives style, required features, and knob defaults from
code (``src/trading/services/strategy_catalog/resolution.py``). The copies were
written from code at create/seed and then carried forward verbatim on update, so
they drift silently when a primitive's code definition changes. ``style`` was
only ever displayed; ``required_features`` had no reader at all.

This is a data-preserving rebuild (unlike the empty research tables in 0016):
``strategies`` holds real rows and is referenced by many foreign keys, so the
column drop uses the SQLite create/copy/drop/rename pattern with an explicit
column list. ``style`` carries a NOT NULL CHECK, which ``ALTER TABLE DROP
COLUMN`` cannot express, so a full rebuild is required.

The downgrade restores the previous shape only: ``style`` is code-derived, not
recoverable from the database alone, so existing rows are repopulated with the
``'neutral'`` placeholder and ``required_features`` with NULL. Re-running
``seed_strategy_catalog`` (or the pre-migration backup) restores the true
code-derived values. Self-contained by convention: literal DDL only.
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Explicit copy list — rebuilds must never use SELECT *.
_KEPT_COLUMNS = (
    "id",
    "strategy_key",
    "primitive",
    "params_json",
    "description",
    "status",
    "enabled",
    "created_at",
    "updated_at",
)

_NEW_TABLE = """
    CREATE TABLE strategies_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_key TEXT NOT NULL UNIQUE,
        primitive TEXT NOT NULL,
        params_json TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'frozen', 'retired')),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

# The 0001 shape, restored by the downgrade (style/required_features re-added).
_OLD_TABLE = """
    CREATE TABLE strategies_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_key TEXT NOT NULL UNIQUE,
        primitive TEXT NOT NULL,
        params_json TEXT NOT NULL,
        style TEXT NOT NULL CHECK (style IN ('trend', 'mean_reversion', 'neutral', 'alternative')),
        required_features TEXT,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'frozen', 'retired')),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""


def _swap_and_check() -> None:
    op.execute("DROP TABLE strategies")
    op.execute("ALTER TABLE strategies_new RENAME TO strategies")
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check(strategies)").fetchall()
    if orphans:
        raise RuntimeError(f"strategies rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    columns = ", ".join(_KEPT_COLUMNS)
    op.execute(_NEW_TABLE)
    op.execute(f"INSERT INTO strategies_new ({columns}) SELECT {columns} FROM strategies")
    _swap_and_check()


def downgrade() -> None:
    # style is restored as the 'neutral' placeholder and required_features as
    # NULL; the true code-derived values come from re-seeding or the backup.
    op.execute(_OLD_TABLE)
    op.execute(
        """
        INSERT INTO strategies_new (
            id, strategy_key, primitive, params_json, style, required_features,
            description, status, enabled, created_at, updated_at
        )
        SELECT
            id, strategy_key, primitive, params_json, 'neutral', NULL,
            description, status, enabled, created_at, updated_at
        FROM strategies
        """
    )
    _swap_and_check()
