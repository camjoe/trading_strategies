"""Data-contract vocabulary for book rotation settings change-audit events."""

from __future__ import annotations

# Which book_rotation_settings upsert wrote a book_rotation_settings_change_events row.
BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING = "scheduling"
BOOK_ROTATION_SETTINGS_GROUP_POLICY = "policy"
