"""Add settings change-audit event tables.

Revision ID: 0025
Revises: 0024

Closes the gap noted in ``docs/overview.md`` ("Known limitations"): a settings
edit previously left only ``updated_at`` behind, with no record of what changed
or from what prior value. Two new event-log tables, one per owning settings
table (mirrors the ``promotion_review_events`` pattern rather than one shared
polymorphic table, per the "typed tables, no generic EAV storage" convention):

``global_settings_change_events`` — one row per edit to the global_settings
singleton (throttle, evaluation, or promotion group), recording only the
fields that actually changed as a compact JSON old/new payload.

``book_rotation_settings_change_events`` — same shape, scoped to a book via
``book_id`` (scheduling or policy group).

Both repositories skip the insert when a write produces no actual field
change (an idempotent re-save of current values), so the trail stays
meaningful rather than accumulating no-op rows.

Self-contained by convention: no application imports, literal DDL only. Two
new tables (pure CREATE); the downgrade drops them.
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE global_settings_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            settings_group TEXT NOT NULL,
            changed_fields TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_global_settings_change_events_created ON global_settings_change_events(created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE book_rotation_settings_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            settings_group TEXT NOT NULL,
            changed_fields TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        """
    )
    # book_id leading column covers the FK cascade lookup; created_at orders history.
    op.execute(
        "CREATE INDEX idx_book_rotation_settings_change_events_book_created "
        "ON book_rotation_settings_change_events(book_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE book_rotation_settings_change_events")
    op.execute("DROP TABLE global_settings_change_events")
