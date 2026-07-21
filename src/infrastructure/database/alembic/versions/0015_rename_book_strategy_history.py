"""Rename book strategy assignments to book strategy history.

Revision ID: 0015
Revises: 0014

The table is the effective-dated history of strategies assigned to each book:
the row with ``effective_to IS NULL`` is current, and closed rows are prior
assignments. ``book_strategy_history`` makes that temporal role explicit and
aligns with ``book_universe_history``.

SQLite preserves the table data and constraints during ``RENAME TO``. The
three indexes are recreated so their names match the renamed table; the
partial unique index continues to enforce one open strategy per book.
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_OLD_INDEXES = (
    "idx_book_assignments_open_per_book",
    "idx_book_assignments_book_effective",
    "idx_book_assignments_strategy_effective",
)

_NEW_INDEXES = (
    (
        "CREATE UNIQUE INDEX idx_book_strategy_history_open_per_book "
        "ON book_strategy_history(book_id) WHERE effective_to IS NULL"
    ),
    ("CREATE INDEX idx_book_strategy_history_book_effective ON book_strategy_history(book_id, effective_from DESC)"),
    (
        "CREATE INDEX idx_book_strategy_history_strategy_effective "
        "ON book_strategy_history(strategy_id, effective_from DESC)"
    ),
)

_RESTORED_INDEXES = (
    (
        "CREATE UNIQUE INDEX idx_book_assignments_open_per_book "
        "ON book_strategy_assignments(book_id) WHERE effective_to IS NULL"
    ),
    ("CREATE INDEX idx_book_assignments_book_effective ON book_strategy_assignments(book_id, effective_from DESC)"),
    (
        "CREATE INDEX idx_book_assignments_strategy_effective "
        "ON book_strategy_assignments(strategy_id, effective_from DESC)"
    ),
)


def _drop_indexes(index_names: tuple[str, ...]) -> None:
    for index_name in index_names:
        op.execute(f"DROP INDEX {index_name}")


def _create_indexes(index_statements: tuple[str, ...]) -> None:
    for index_statement in index_statements:
        op.execute(index_statement)


def upgrade() -> None:
    _drop_indexes(_OLD_INDEXES)
    op.execute("ALTER TABLE book_strategy_assignments RENAME TO book_strategy_history")
    _create_indexes(_NEW_INDEXES)


def downgrade() -> None:
    _drop_indexes(
        (
            "idx_book_strategy_history_open_per_book",
            "idx_book_strategy_history_book_effective",
            "idx_book_strategy_history_strategy_effective",
        )
    )
    op.execute("ALTER TABLE book_strategy_history RENAME TO book_strategy_assignments")
    _create_indexes(_RESTORED_INDEXES)
