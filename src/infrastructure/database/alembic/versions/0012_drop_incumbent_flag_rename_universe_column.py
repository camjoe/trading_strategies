"""Drop the redundant assignment incumbent flag; rename the universe column.

Revision ID: 0012
Revises: 0011

Two independent legibility fixes from the schema final-overview:

- ``book_strategy_assignments.is_incumbent`` is dropped. "Incumbent" is by
  definition the book's open assignment, which is already carried by
  ``effective_to IS NULL`` and structurally enforced by the partial unique
  index ``idx_book_assignments_open_per_book`` (one open row per book). The
  boolean was a second, drift-prone encoding of that same fact that nothing
  read for logic. Because it carries a CHECK constraint, SQLite cannot drop it
  in place, so this is an explicit copy-and-rebuild that preserves the two FKs
  and all three indexes.
- ``book_universe_history.universes_json`` is renamed to ``trade_universes`` so
  it matches the ``books.trade_universes`` column it mirrors (the two held the
  same concept under two names). A pure ``RENAME COLUMN``: the table's indexes
  key on ``book_id``/``effective_from``, never this column, so no rebuild is
  required.

Self-contained by convention: literal DDL only, no application imports. The
rebuild uses an explicit column list (never SELECT *).
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# Explicit copy list for the rebuild WITHOUT is_incumbent.
_ASSIGNMENT_COLUMNS = (
    "id",
    "book_id",
    "strategy_id",
    "effective_from",
    "effective_to",
    "created_at",
    "updated_at",
)

# Target shape (no is_incumbent). Matches the 0001 contract otherwise.
_ASSIGNMENTS_DDL_NO_FLAG = """
    CREATE TABLE book_strategy_assignments_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        strategy_id INTEGER NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id)
    )
"""

# Downgrade shape (is_incumbent restored, backfilled from effective_to).
_ASSIGNMENTS_DDL_WITH_FLAG = """
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
"""

_ASSIGNMENTS_INDEXES = (
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


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0012 rebuild left FK violations: {orphans!r}")


def _rebuild_assignments(*, ddl: str, insert_columns: str, select_expr: str) -> None:
    op.execute(ddl)
    op.execute(
        f"INSERT INTO book_strategy_assignments_new ({insert_columns}) "
        f"SELECT {select_expr} FROM book_strategy_assignments"
    )
    op.execute("DROP TABLE book_strategy_assignments")
    op.execute("ALTER TABLE book_strategy_assignments_new RENAME TO book_strategy_assignments")
    for index_sql in _ASSIGNMENTS_INDEXES:
        op.execute(index_sql)


def upgrade() -> None:
    column_list = ", ".join(_ASSIGNMENT_COLUMNS)
    _rebuild_assignments(ddl=_ASSIGNMENTS_DDL_NO_FLAG, insert_columns=column_list, select_expr=column_list)
    op.execute("ALTER TABLE book_universe_history RENAME COLUMN universes_json TO trade_universes")
    _check_foreign_keys()


def downgrade() -> None:
    # Restores the 0011 shapes. is_incumbent is reconstructed from the open-row
    # invariant: the open assignment (effective_to IS NULL) is the incumbent.
    op.execute("ALTER TABLE book_universe_history RENAME COLUMN trade_universes TO universes_json")
    insert_columns = ", ".join((*_ASSIGNMENT_COLUMNS, "is_incumbent"))
    select_expr = ", ".join((*_ASSIGNMENT_COLUMNS, "CASE WHEN effective_to IS NULL THEN 1 ELSE 0 END"))
    _rebuild_assignments(ddl=_ASSIGNMENTS_DDL_WITH_FLAG, insert_columns=insert_columns, select_expr=select_expr)
    _check_foreign_keys()
