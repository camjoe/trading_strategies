"""Tests for trading.services.runtime_throttle.enforcement."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.services.runtime_settings.models import RuntimeThrottleSettings
from trading.services.runtime_throttle.enforcement import enforce_runtime_trade_throttles


def _settings(*, day: int | None = None, minute: int | None = None) -> RuntimeThrottleSettings:
    return RuntimeThrottleSettings(max_trades_per_day=day, max_trades_per_minute=minute)


class TestEnforceRuntimeTradeThrottles:
    def test_non_connection_object_returns_immediately(self) -> None:
        """No execute attr → early return, no checks performed."""
        enforce_runtime_trade_throttles(
            object(),  # type: ignore[arg-type]
            trade_time_iso="2026-01-15T10:00:00Z",
        )

    def test_both_limits_none_skips_count_queries(self, conn: sqlite3.Connection) -> None:
        """Neither limit set → no DB trade count needed."""
        fetch_fn = MagicMock(return_value=_settings(day=None, minute=None))
        count_fn = MagicMock(return_value=0)
        enforce_runtime_trade_throttles(
            conn,
            trade_time_iso="2026-01-15T10:00:00Z",
            fetch_runtime_throttle_settings_fn=fetch_fn,
            count_trades_between_fn=count_fn,
        )
        count_fn.assert_not_called()

    def test_day_limit_exceeded_raises(self, conn: sqlite3.Connection) -> None:
        """Daily count >= limit → RuntimeTradeThrottleExceededError."""
        fetch_fn = MagicMock(return_value=_settings(day=5, minute=None))
        count_fn = MagicMock(return_value=5)
        with pytest.raises(RuntimeTradeThrottleExceededError, match="per_day"):
            enforce_runtime_trade_throttles(
                conn,
                trade_time_iso="2026-01-15T10:00:00Z",
                fetch_runtime_throttle_settings_fn=fetch_fn,
                count_trades_between_fn=count_fn,
            )

    def test_day_limit_not_reached_passes(self, conn: sqlite3.Connection) -> None:
        fetch_fn = MagicMock(return_value=_settings(day=10, minute=None))
        count_fn = MagicMock(return_value=4)
        enforce_runtime_trade_throttles(
            conn,
            trade_time_iso="2026-01-15T10:00:00Z",
            fetch_runtime_throttle_settings_fn=fetch_fn,
            count_trades_between_fn=count_fn,
        )

    def test_minute_limit_exceeded_raises(self, conn: sqlite3.Connection) -> None:
        fetch_fn = MagicMock(return_value=_settings(day=None, minute=3))
        count_fn = MagicMock(return_value=3)
        with pytest.raises(RuntimeTradeThrottleExceededError, match="per_minute"):
            enforce_runtime_trade_throttles(
                conn,
                trade_time_iso="2026-01-15T10:00:00Z",
                fetch_runtime_throttle_settings_fn=fetch_fn,
                count_trades_between_fn=count_fn,
            )

    def test_both_limits_set_day_checked_first(self, conn: sqlite3.Connection) -> None:
        """When both limits are set and day limit is exceeded, it raises before minute check."""
        fetch_fn = MagicMock(return_value=_settings(day=2, minute=2))
        count_fn = MagicMock(return_value=2)
        with pytest.raises(RuntimeTradeThrottleExceededError, match="per_day"):
            enforce_runtime_trade_throttles(
                conn,
                trade_time_iso="2026-01-15T10:00:00Z",
                fetch_runtime_throttle_settings_fn=fetch_fn,
                count_trades_between_fn=count_fn,
            )
