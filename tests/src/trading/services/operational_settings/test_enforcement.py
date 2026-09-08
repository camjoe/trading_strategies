"""Tests for trading.services.operational_settings.enforcement."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import ensure_default_book_id
from tests.support.repositories import insert_repository_account
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.models.orders import OrderInsert
from trading.repositories.orders import OrderRepository
from trading.services.operational_settings.enforcement import enforce_runtime_trade_throttles
from trading.services.operational_settings.mutations import set_runtime_throttle_settings

NOW = "2026-01-15T10:00:00Z"
IN_WINDOW = "2026-01-15T09:59:30Z"


@pytest.fixture
def book(conn: sqlite3.Connection) -> tuple[int, int]:
    account_id = insert_repository_account(conn, name="throttle_acct")
    return account_id, ensure_default_book_id(conn, account_id)


def _limits(conn: sqlite3.Connection, *, day: int | None = None, minute: int | None = None) -> None:
    set_runtime_throttle_settings(
        conn,
        runtime_max_trades_per_day=day,
        runtime_max_trades_per_minute=minute,
        updated_at=NOW,
    )


def _submit(conn: sqlite3.Connection, book: tuple[int, int], *, count: int, fill: bool) -> None:
    """Submit ``count`` orders inside the throttle window, filling each when asked."""
    account_id, book_id = book
    repo = OrderRepository(conn)
    for index in range(count):
        order_id = repo.insert(
            OrderInsert(
                book_id=book_id,
                account_id=account_id,
                symbol=f"SYM{index}",
                side="buy",
                qty=1.0,
                status="filled" if fill else "submitted",
                submitted_at=IN_WINDOW,
                updated_at=IN_WINDOW,
            )
        )
        if fill:
            repo.insert_fill(order_id=order_id, filled_qty=1.0, fill_price=10.0, fill_time=IN_WINDOW)


class TestEnforceRuntimeTradeThrottles:
    def test_no_limits_set_allows_any_volume(self, conn: sqlite3.Connection, book: tuple[int, int]) -> None:
        _submit(conn, book, count=5, fill=True)
        enforce_runtime_trade_throttles(conn, trade_time_iso=NOW)

    def test_day_limit_reached_raises(self, conn: sqlite3.Connection, book: tuple[int, int]) -> None:
        _limits(conn, day=3)
        _submit(conn, book, count=3, fill=True)
        with pytest.raises(RuntimeTradeThrottleExceededError, match="per_day"):
            enforce_runtime_trade_throttles(conn, trade_time_iso=NOW)

    def test_day_limit_not_reached_passes(self, conn: sqlite3.Connection, book: tuple[int, int]) -> None:
        _limits(conn, day=3)
        _submit(conn, book, count=2, fill=True)
        enforce_runtime_trade_throttles(conn, trade_time_iso=NOW)

    def test_day_limit_counts_fills_not_submissions(self, conn: sqlite3.Connection, book: tuple[int, int]) -> None:
        """The daily cap measures trading done, so unfilled orders do not count against it."""
        _limits(conn, day=2)
        _submit(conn, book, count=5, fill=False)
        enforce_runtime_trade_throttles(conn, trade_time_iso=NOW)

    def test_minute_limit_counts_submissions_not_fills(self, conn: sqlite3.Connection, book: tuple[int, int]) -> None:
        """Broker pacing measures requests sent. An order that never fills still cost one."""
        _limits(conn, minute=3)
        _submit(conn, book, count=3, fill=False)
        with pytest.raises(RuntimeTradeThrottleExceededError, match="per_minute"):
            enforce_runtime_trade_throttles(conn, trade_time_iso=NOW)

    def test_submissions_outside_the_minute_window_do_not_count(
        self, conn: sqlite3.Connection, book: tuple[int, int]
    ) -> None:
        _limits(conn, minute=2)
        _submit(conn, book, count=3, fill=False)
        # Two minutes on, the earlier submissions have left the rolling window.
        enforce_runtime_trade_throttles(conn, trade_time_iso="2026-01-15T10:02:00Z")

    def test_day_limit_is_checked_before_the_minute_limit(
        self, conn: sqlite3.Connection, book: tuple[int, int]
    ) -> None:
        _limits(conn, day=2, minute=2)
        _submit(conn, book, count=2, fill=True)
        with pytest.raises(RuntimeTradeThrottleExceededError, match="per_day"):
            enforce_runtime_trade_throttles(conn, trade_time_iso=NOW)
