"""Market-hours helpers for exchange-aware trading guards."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

US_EQUITY_MARKET_TIMEZONE = ZoneInfo("America/New_York")
US_EQUITY_MARKET_OPEN_TIME = time(hour=9, minute=30)
US_EQUITY_MARKET_CLOSE_TIME = time(hour=16, minute=0)
US_EQUITY_EARLY_CLOSE_TIME = time(hour=13, minute=0)
US_EQUITY_FIRST_TRADING_WEEKDAY = 0
US_EQUITY_LAST_TRADING_WEEKDAY = 4
JUNETEENTH_START_YEAR = 2022


def is_regular_us_equity_market_open(at: datetime | None = None) -> bool:
    current = at or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Market-hours checks require a timezone-aware datetime.")

    eastern = current.astimezone(US_EQUITY_MARKET_TIMEZONE)
    current_date = eastern.date()
    if not _is_us_equity_trading_day(current_date):
        return False

    current_time = eastern.timetz().replace(tzinfo=None)
    return US_EQUITY_MARKET_OPEN_TIME <= current_time < _market_close_time_for_date(current_date)


def _is_us_equity_trading_day(current_date: date) -> bool:
    if current_date.weekday() < US_EQUITY_FIRST_TRADING_WEEKDAY:
        return False
    if current_date.weekday() > US_EQUITY_LAST_TRADING_WEEKDAY:
        return False
    return current_date not in _nyse_full_day_holidays(current_date.year, current_date.year + 1)


def _market_close_time_for_date(current_date: date) -> time:
    if current_date in _nyse_early_close_days(current_date.year):
        return US_EQUITY_EARLY_CLOSE_TIME
    return US_EQUITY_MARKET_CLOSE_TIME


def _nyse_full_day_holidays(*years: int) -> set[date]:
    holidays: set[date] = set()
    for year in years:
        holidays.add(_observed_fixed_holiday(date(year, 1, 1)))
        holidays.add(_nth_weekday_of_month(year, 1, weekday=0, occurrence=3))
        holidays.add(_nth_weekday_of_month(year, 2, weekday=0, occurrence=3))
        holidays.add(_good_friday(year))
        holidays.add(_last_weekday_of_month(year, 5, weekday=0))
        if year >= JUNETEENTH_START_YEAR:
            holidays.add(_observed_fixed_holiday(date(year, 6, 19)))
        holidays.add(_observed_fixed_holiday(date(year, 7, 4)))
        holidays.add(_nth_weekday_of_month(year, 9, weekday=0, occurrence=1))
        holidays.add(_nth_weekday_of_month(year, 11, weekday=3, occurrence=4))
        holidays.add(_observed_fixed_holiday(date(year, 12, 25)))
    return holidays


def _nyse_early_close_days(year: int) -> set[date]:
    early_closes: set[date] = set()

    independence_day = date(year, 7, 4)
    if independence_day.weekday() in {1, 2, 3, 4}:
        early_closes.add(independence_day - timedelta(days=1))

    thanksgiving = _nth_weekday_of_month(year, 11, weekday=3, occurrence=4)
    early_closes.add(thanksgiving + timedelta(days=1))

    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() <= 3 and christmas_eve != _observed_fixed_holiday(date(year, 12, 25)):
        early_closes.add(christmas_eve)

    return early_closes


def _observed_fixed_holiday(actual: date) -> date:
    if actual.weekday() == 5:
        return actual - timedelta(days=1)
    if actual.weekday() == 6:
        return actual + timedelta(days=1)
    return actual


def _nth_weekday_of_month(year: int, month: int, *, weekday: int, occurrence: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    current += timedelta(weeks=occurrence - 1)
    return current


def _last_weekday_of_month(year: int, month: int, *, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _good_friday(year: int) -> date:
    return _easter_sunday(year) - timedelta(days=2)


def _easter_sunday(year: int) -> date:
    century = year // 100
    year_in_century = year % 100
    leap_centuries = century // 4
    century_remainder = century % 4
    correction = (century + 8) // 25
    moon_offset = (century - correction + 1) // 3
    epact = (19 * (year % 19) + century - leap_centuries - moon_offset + 15) % 30
    leap_years = year_in_century // 4
    year_remainder = year_in_century % 4
    weekday_offset = (32 + 2 * century_remainder + 2 * leap_years - epact - year_remainder) % 7
    month_adjustment = (year % 19 + 11 * epact + 22 * weekday_offset) // 451
    month = (epact + weekday_offset - 7 * month_adjustment + 114) // 31
    day = ((epact + weekday_offset - 7 * month_adjustment + 114) % 31) + 1
    return date(year, month, day)
