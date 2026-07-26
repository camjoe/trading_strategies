from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BookRotationSettingsChangeEvent:
    """One audited edit to a book_rotation_settings field: prior/new value, when.

    ``changed_fields`` holds only fields whose value actually changed, keyed by
    field name to ``{"old": ..., "new": ...}``.
    """

    id: int
    book_id: int
    settings_group: str
    changed_fields: dict[str, dict[str, object]]
    created_at: str
