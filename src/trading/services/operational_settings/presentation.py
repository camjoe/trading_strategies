"""CLI-facing presentation for operational settings."""

from __future__ import annotations

import sqlite3

from trading.models.settings import GlobalSettingsChangeEvent
from trading.services.change_history_presentation import render_settings_change_lines
from trading.services.operational_settings.queries import fetch_global_settings_change_history


def show_global_settings_history(conn: sqlite3.Connection, *, limit: int = 20) -> list[GlobalSettingsChangeEvent]:
    """Print the global settings change-audit trail (latest first) and return it."""
    events = fetch_global_settings_change_history(conn, limit=limit)
    if not events:
        print("No global settings changes recorded.")
        return events

    print(f"Global settings change history (latest {limit}):")
    for line in render_settings_change_lines(events):
        print(line)
    return events


__all__ = ["show_global_settings_history"]
