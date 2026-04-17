from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.coercion import row_int
from trading.repositories.global_settings_repository import fetch_global_settings_row


@dataclass(frozen=True)
class RuntimeThrottleSettings:
    max_trades_per_day: int | None = None
    max_trades_per_minute: int | None = None


def fetch_runtime_throttle_settings(conn: sqlite3.Connection) -> RuntimeThrottleSettings:
    row = fetch_global_settings_row(conn)
    if row is None:
        return RuntimeThrottleSettings()
    return RuntimeThrottleSettings(
        max_trades_per_day=row_int(row, "runtime_max_trades_per_day"),
        max_trades_per_minute=row_int(row, "runtime_max_trades_per_minute"),
    )
