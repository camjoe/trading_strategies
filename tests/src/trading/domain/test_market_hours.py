from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from trading.domain.market.hours import add_us_equity_trading_days, is_regular_us_equity_market_open


def test_market_open_during_regular_weekday_session() -> None:
    assert is_regular_us_equity_market_open(datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc))


def test_market_closed_before_open() -> None:
    assert not is_regular_us_equity_market_open(datetime(2026, 3, 16, 13, 29, tzinfo=timezone.utc))


def test_market_closed_on_weekend() -> None:
    assert not is_regular_us_equity_market_open(datetime(2026, 3, 14, 15, 0, tzinfo=timezone.utc))


def test_market_closed_on_good_friday() -> None:
    assert not is_regular_us_equity_market_open(datetime(2026, 4, 3, 15, 0, tzinfo=timezone.utc))


def test_market_closed_on_observed_new_year_holiday() -> None:
    assert not is_regular_us_equity_market_open(datetime(2021, 12, 31, 15, 0, tzinfo=timezone.utc))


def test_market_hours_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        is_regular_us_equity_market_open(datetime(2026, 3, 16, 14, 0))


def test_market_closed_after_thanksgiving_early_close() -> None:
    assert not is_regular_us_equity_market_open(datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc))


def test_market_open_before_thanksgiving_early_close() -> None:
    assert is_regular_us_equity_market_open(datetime(2026, 11, 27, 17, 30, tzinfo=timezone.utc))


def test_market_closed_after_independence_day_eve_early_close() -> None:
    assert not is_regular_us_equity_market_open(datetime(2026, 7, 3, 17, 30, tzinfo=timezone.utc))


def test_market_closed_after_christmas_eve_early_close() -> None:
    assert not is_regular_us_equity_market_open(datetime(2026, 12, 24, 18, 30, tzinfo=timezone.utc))


def test_add_trading_days_skips_the_weekend() -> None:
    # Friday 2026-10-02 + 1 trading day is Monday 2026-10-05.
    assert add_us_equity_trading_days(date(2026, 10, 2), 1) == date(2026, 10, 5)


def test_add_trading_days_skips_a_full_holiday() -> None:
    # Wednesday 2026-11-25 + 1 trading day skips Thanksgiving (2026-11-26) to Friday.
    assert add_us_equity_trading_days(date(2026, 11, 25), 1) == date(2026, 11, 27)


def test_add_zero_trading_days_is_the_start() -> None:
    assert add_us_equity_trading_days(date(2026, 10, 3), 0) == date(2026, 10, 3)


def test_add_trading_days_rejects_negative() -> None:
    with pytest.raises(ValueError):
        add_us_equity_trading_days(date(2026, 10, 2), -1)
