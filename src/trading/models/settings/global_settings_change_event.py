from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GlobalSettingsChangeEvent:
    """One audited edit to a global_settings field: prior and new value, when.

    ``changed_fields`` holds only fields whose value actually changed, keyed by
    field name to ``{"old": ..., "new": ...}``.
    """

    id: int
    settings_group: str
    changed_fields: dict[str, dict[str, object]]
    created_at: str
