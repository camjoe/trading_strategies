from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading.domain.market.hours import is_regular_us_equity_market_open


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
