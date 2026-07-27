"""Read orchestration for the global settings change-audit trail."""

from __future__ import annotations

import sqlite3

from trading.models.settings.global_settings_change_event import GlobalSettingsChangeEvent
from trading.repositories.global_settings import GlobalSettingsRepository


def fetch_global_settings_change_history(
    conn: sqlite3.Connection, *, limit: int = 20
) -> list[GlobalSettingsChangeEvent]:
    return GlobalSettingsRepository(conn).fetch_change_events(limit=limit)


__all__ = ["fetch_global_settings_change_history"]
