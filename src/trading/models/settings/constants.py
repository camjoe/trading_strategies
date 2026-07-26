"""Data-contract vocabulary for global settings change-audit events."""

from __future__ import annotations

# Which global_settings upsert wrote a global_settings_change_events row.
GLOBAL_SETTINGS_GROUP_THROTTLE = "throttle"
GLOBAL_SETTINGS_GROUP_EVALUATION = "evaluation"
GLOBAL_SETTINGS_GROUP_PROMOTION = "promotion"
