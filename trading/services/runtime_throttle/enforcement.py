"""Runtime throttle enforcement helpers for runtime-throttle consumers."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Callable

from common.time import as_utc_iso
from common.time import parse_utc_iso
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.repositories.trades import count_trades_between
from trading.services.runtime_settings import RuntimeThrottleSettings, fetch_runtime_throttle_settings

# Rolling one-minute window for the per-minute global runtime trade cap.
TRADE_THROTTLE_MINUTE_WINDOW = timedelta(minutes=1)


def enforce_runtime_trade_throttles(
    conn: sqlite3.Connection,
    *,
    trade_time_iso: str,
    fetch_runtime_throttle_settings_fn: Callable[
        [sqlite3.Connection], RuntimeThrottleSettings
    ] = fetch_runtime_throttle_settings,
    count_trades_between_fn: Callable[[sqlite3.Connection, str, str], int] = count_trades_between,
) -> None:
    if not hasattr(conn, "execute"):
        return

    settings = fetch_runtime_throttle_settings_fn(conn)
    if settings.max_trades_per_day is None and settings.max_trades_per_minute is None:
        return

    trade_time = parse_utc_iso(trade_time_iso)
    trade_time_utc = as_utc_iso(trade_time)

    if settings.max_trades_per_day is not None:
        day_start = trade_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = count_trades_between_fn(conn, as_utc_iso(day_start), trade_time_utc)
        if day_count >= settings.max_trades_per_day:
            raise RuntimeTradeThrottleExceededError(
                f"Global runtime trade throttle reached: runtime_max_trades_per_day={settings.max_trades_per_day}."
            )

    if settings.max_trades_per_minute is not None:
        window_start = trade_time - TRADE_THROTTLE_MINUTE_WINDOW
        minute_count = count_trades_between_fn(conn, as_utc_iso(window_start), trade_time_utc)
        if minute_count >= settings.max_trades_per_minute:
            raise RuntimeTradeThrottleExceededError(
                "Global runtime trade throttle reached: "
                f"runtime_max_trades_per_minute={settings.max_trades_per_minute}."
            )


__all__ = [
    "RuntimeThrottleSettings",
    "TRADE_THROTTLE_MINUTE_WINDOW",
    "enforce_runtime_trade_throttles",
]
