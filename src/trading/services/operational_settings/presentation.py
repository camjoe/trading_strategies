"""CLI-facing presentation for operational settings."""

from __future__ import annotations

import sqlite3

from trading.models.settings import GlobalSettingsChangeEvent
from trading.services.operational_settings.queries import fetch_global_settings_change_history


def show_global_settings_history(conn: sqlite3.Connection, *, limit: int = 20) -> list[GlobalSettingsChangeEvent]:
    """Print the global settings change-audit trail (latest first) and return it."""
    events = fetch_global_settings_change_history(conn, limit=limit)
    if not events:
        print("No global settings changes recorded.")
        return events

    print(f"Global settings change history (latest {limit}):")
    for event in events:
        rendered = ", ".join(
            f"{field}: {change['old']!r} -> {change['new']!r}" for field, change in event.changed_fields.items()
        )
        print(f"- {event.created_at} | {event.settings_group} | {rendered}")
    return events


__all__ = ["show_global_settings_history"]
