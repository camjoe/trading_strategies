"""Drop the five never-populated rotation_decisions columns.

Revision ID: 0013
Revises: 0012

``rotation_decisions`` reserved five first-class columns that no writer ever
populated (always NULL) and no reader ever consumed:

- ``decision_score``     — duplicate of ``score_components_json[selected].total_score``
- ``decision_confidence`` — rotation has no confidence concept (that lives in the
  evaluation/promotion subsystem)
- ``window_start`` / ``window_end`` — the strategy-active evaluation window, which
  the evaluation layer already derives on the fly from the decision timeline plus
  ``equity_snapshots`` (``services/evaluation/evidence.py``)
- ``realized_pnl_delta`` — the post-decision outcome, likewise derivable from
  ``equity_snapshots`` and ``decision_time``

They were a denormalized read-model cache with no read model. The retained
columns (the strategy FKs, ``rotation_action``, ``cooldown_active``,
``score_components_json``, ``gate_results_json``, ``decision_reason``,
``config_version``) still carry the full decision provenance; a future rotation
audit reader will populate first-class columns then, deliberately, with a
consumer.

SQLite cannot drop a column that participates in a CHECK constraint in place,
and this table is the parent of ``orders.rotation_decision_id`` (revision 0009),
so this is an explicit copy-and-rebuild — the same shape as revision 0002, which
is the rotation_decisions rebuild precedent — reproducing the book ON DELETE
CASCADE and the three strategy FKs. Self-contained by convention: literal DDL
only, explicit column list (never SELECT *).
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# Retained columns (the five reserved slots removed). Order matches the table.
_KEPT_COLUMNS = (
    "id",
    "book_id",
    "decision_time",
    "incumbent_strategy_id",
    "challenger_strategy_id",
    "selected_strategy_id",
    "rotation_action",
    "cooldown_active",
    "score_components_json",
    "gate_results_json",
    "decision_reason",
    "config_version",
    "created_at",
)

_DDL_WITHOUT_RESERVED = """
    CREATE TABLE rotation_decisions_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        decision_time TEXT NOT NULL,
        incumbent_strategy_id INTEGER,
        challenger_strategy_id INTEGER,
        selected_strategy_id INTEGER,
        rotation_action TEXT NOT NULL CHECK (rotation_action IN ('hold', 'rotate')),
        cooldown_active INTEGER NOT NULL DEFAULT 0,
        score_components_json TEXT NOT NULL,
        gate_results_json TEXT NOT NULL,
        decision_reason TEXT,
        config_version TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (incumbent_strategy_id) REFERENCES strategies(id),
        FOREIGN KEY (challenger_strategy_id) REFERENCES strategies(id),
        FOREIGN KEY (selected_strategy_id) REFERENCES strategies(id)
    )
"""

# Downgrade shape: the five reserved columns restored as nullable (their only
# ever value), matching the 0012 contract.
_DDL_WITH_RESERVED = """
    CREATE TABLE rotation_decisions_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        decision_time TEXT NOT NULL,
        incumbent_strategy_id INTEGER,
        challenger_strategy_id INTEGER,
        selected_strategy_id INTEGER,
        rotation_action TEXT NOT NULL CHECK (rotation_action IN ('hold', 'rotate')),
        cooldown_active INTEGER NOT NULL DEFAULT 0,
        decision_score REAL,
        decision_confidence REAL,
        score_components_json TEXT NOT NULL,
        gate_results_json TEXT NOT NULL,
        decision_reason TEXT,
        config_version TEXT,
        window_start TEXT,
        window_end TEXT,
        realized_pnl_delta REAL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (incumbent_strategy_id) REFERENCES strategies(id),
        FOREIGN KEY (challenger_strategy_id) REFERENCES strategies(id),
        FOREIGN KEY (selected_strategy_id) REFERENCES strategies(id)
    )
"""

_INDEXES = (
    "CREATE INDEX idx_rotation_decisions_book_time ON rotation_decisions(book_id, decision_time DESC)",
    (
        "CREATE INDEX idx_rotation_decisions_action_time_book "
        "ON rotation_decisions(rotation_action, decision_time DESC)"
    ),
)


def _rebuild(*, ddl: str) -> None:
    # Only the retained columns are ever copied; the dropped slots were always
    # NULL, so nothing is lost on upgrade and they come back NULL on downgrade.
    column_list = ", ".join(_KEPT_COLUMNS)
    op.execute(ddl)
    op.execute(f"INSERT INTO rotation_decisions_new ({column_list}) SELECT {column_list} FROM rotation_decisions")
    op.execute("DROP TABLE rotation_decisions")
    op.execute("ALTER TABLE rotation_decisions_new RENAME TO rotation_decisions")
    for index_sql in _INDEXES:
        op.execute(index_sql)
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0013 rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    _rebuild(ddl=_DDL_WITHOUT_RESERVED)


def downgrade() -> None:
    # Restores the 0012 shape; the five reserved columns return empty (NULL),
    # which is the only value they ever held.
    _rebuild(ddl=_DDL_WITH_RESERVED)
