"""Trade throttle enforcement helpers for operational-settings consumers."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from common.time import as_utc_iso, parse_utc_iso
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.repositories.orders import OrderRepository
from trading.services.operational_settings.models import RuntimeThrottleSettings
from trading.services.operational_settings.queries import fetch_runtime_throttle_settings

# Rolling one-minute window for the per-minute global runtime trade cap.
TRADE_THROTTLE_MINUTE_WINDOW = timedelta(minutes=1)


def enforce_runtime_trade_throttles(conn: sqlite3.Connection, *, trade_time_iso: str) -> None:
    settings = fetch_runtime_throttle_settings(conn)
    if settings.max_trades_per_day is None and settings.max_trades_per_minute is None:
        return

    orders = OrderRepository(conn)
    trade_time = parse_utc_iso(trade_time_iso)
    trade_time_utc = as_utc_iso(trade_time)

    # Per-day measures trading done, so it counts fills. Per-minute is broker
    # pacing, so it counts orders sent — an unfilled order still cost a request.
    if settings.max_trades_per_day is not None:
        day_start = trade_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = orders.fetch_fill_count_between(start_iso=as_utc_iso(day_start), end_iso=trade_time_utc)
        if day_count >= settings.max_trades_per_day:
            raise RuntimeTradeThrottleExceededError(
                f"Global runtime trade throttle reached: runtime_max_trades_per_day={settings.max_trades_per_day}."
            )

    if settings.max_trades_per_minute is not None:
        window_start = trade_time - TRADE_THROTTLE_MINUTE_WINDOW
        minute_count = orders.fetch_submission_count_between(
            start_iso=as_utc_iso(window_start), end_iso=trade_time_utc
        )
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
