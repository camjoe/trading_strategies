from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Collection

import pytest

from tests.support.books import build_book_env
from tests.support.repositories import insert_repository_account
from trading.repositories.accounts import AccountRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.operations.account_freshness import (
    DEFAULT_FAIL_AFTER_WEEKDAYS,
    DEFAULT_WARN_AFTER_WEEKDAYS,
    AccountFreshness,
    FreshnessReport,
    evaluate_account_freshness,
    weekdays_since,
)

FRIDAY = dt.date(2026, 10, 16)
NEXT_MONDAY = dt.date(2026, 10, 19)


@pytest.mark.parametrize(
    ("last", "as_of", "expected"),
    [
        (dt.date(2026, 10, 16), dt.date(2026, 10, 16), 0),  # Friday to the same Friday
        (dt.date(2026, 10, 16), dt.date(2026, 10, 19), 1),  # Friday to Monday
        (dt.date(2026, 10, 14), dt.date(2026, 10, 16), 2),  # Wednesday to Friday
        (dt.date(2026, 10, 9), dt.date(2026, 10, 16), 5),  # Friday to the next Friday
        (dt.date(2026, 10, 17), dt.date(2026, 10, 19), 1),  # Saturday to Monday
        (dt.date(2026, 10, 15), dt.date(2026, 10, 18), 1),  # Thursday to Sunday: only Friday counts
        (dt.date(2026, 10, 17), dt.date(2026, 10, 18), 0),  # Saturday to Sunday
        (dt.date(2026, 10, 19), dt.date(2026, 10, 16), 0),  # last after as_of
    ],
)
def test_weekdays_since(last: dt.date, as_of: dt.date, expected: int) -> None:
    assert weekdays_since(last, as_of) == expected


def _snapshot_account(conn: sqlite3.Connection, name: str, snapshot_date: str) -> None:
    build_book_env(conn, account_name=name, snapshot_time=f"{snapshot_date}T13:59:00Z")


def _evaluate(
    conn: sqlite3.Connection,
    *,
    as_of: dt.date,
    warn_after: int = DEFAULT_WARN_AFTER_WEEKDAYS,
    fail_after: int = DEFAULT_FAIL_AFTER_WEEKDAYS,
    exclude: Collection[str] = (),
) -> FreshnessReport:
    return evaluate_account_freshness(
        AccountRepository(conn).fetch_all(),
        EquitySnapshotRepository(conn),
        as_of=as_of,
        warn_after=warn_after,
        fail_after=fail_after,
        exclude=exclude,
    )


def test_fresh_account_is_not_reported(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "fresh", "2026-10-16")
    report = _evaluate(conn, as_of=FRIDAY)
    assert (report.warn, report.fail, report.never) == ([], [], [])


def test_warn_and_fail_thresholds_are_inclusive(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "one_under_warn", "2026-10-15")  # 1 weekday
    _snapshot_account(conn, "at_warn", "2026-10-14")  # 2 weekdays
    _snapshot_account(conn, "one_under_fail", "2026-10-12")  # 4 weekdays
    _snapshot_account(conn, "at_fail", "2026-10-09")  # 5 weekdays
    report = _evaluate(conn, as_of=FRIDAY)
    assert [a.account_name for a in report.warn] == ["at_warn", "one_under_fail"]
    assert [a.account_name for a in report.fail] == ["at_fail"]
    assert report.never == []


def test_report_carries_last_snapshot_date_and_staleness(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "stale", "2026-10-09")
    report = _evaluate(conn, as_of=FRIDAY)
    assert report.fail == [AccountFreshness("stale", dt.date(2026, 10, 9), 5)]


def _add_snapshot(conn: sqlite3.Connection, book_id: int, snapshot_time: str) -> None:
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_id,
        snapshot_time=snapshot_time,
        cash=1_000.0,
        market_value=0.0,
        equity=1_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


def test_newest_snapshot_is_used_not_the_oldest(conn: sqlite3.Connection) -> None:
    env = build_book_env(conn, account_name="long_history", snapshot_time="2026-09-01T13:59:00Z")
    _add_snapshot(conn, env.book_id, "2026-10-16T13:59:00Z")
    _add_snapshot(conn, env.book_id, "2026-10-02T13:59:00Z")
    report = _evaluate(conn, as_of=FRIDAY)
    assert (report.warn, report.fail, report.never) == ([], [], [])


def test_snapshot_time_is_converted_to_utc_date(conn: sqlite3.Connection) -> None:
    build_book_env(conn, account_name="behind_utc", snapshot_time="2026-10-15T23:30:00-05:00")
    build_book_env(conn, account_name="ahead_of_utc", snapshot_time="2026-10-16T00:30:00+02:00")
    report = _evaluate(conn, as_of=FRIDAY, warn_after=1)
    assert report.warn == [AccountFreshness("ahead_of_utc", dt.date(2026, 10, 15), 1)]
    assert (report.fail, report.never) == ([], [])


def test_weekend_gap_does_not_count(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "friday_run", "2026-10-16")
    report = _evaluate(conn, as_of=NEXT_MONDAY)
    assert (report.warn, report.fail, report.never) == ([], [], [])


def test_account_without_snapshot_is_listed_as_never(conn: sqlite3.Connection) -> None:
    insert_repository_account(conn, name="brand_new")
    report = _evaluate(conn, as_of=FRIDAY)
    assert report.never == [AccountFreshness("brand_new", None, None)]
    assert (report.warn, report.fail) == ([], [])


def test_excluded_account_is_left_out_of_every_list(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "left_out_stale", "2026-10-02")
    insert_repository_account(conn, name="left_out_new")
    _snapshot_account(conn, "kept_stale", "2026-10-02")
    report = _evaluate(conn, as_of=FRIDAY, exclude=("left_out_stale", "left_out_new"))
    assert [a.account_name for a in report.fail] == ["kept_stale"]
    assert (report.warn, report.never) == ([], [])


def test_several_stale_accounts_each_appear_once(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "a_warn", "2026-10-14")
    _snapshot_account(conn, "b_fail", "2026-10-01")
    _snapshot_account(conn, "c_fail", "2026-10-05")
    insert_repository_account(conn, name="d_never")
    report = _evaluate(conn, as_of=FRIDAY)
    assert [a.account_name for a in report.warn] == ["a_warn"]
    assert [a.account_name for a in report.fail] == ["b_fail", "c_fail"]
    assert [a.account_name for a in report.never] == ["d_never"]


def test_custom_thresholds(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "two_stale", "2026-10-14")
    _snapshot_account(conn, "one_stale", "2026-10-15")
    report = _evaluate(conn, as_of=FRIDAY, warn_after=1, fail_after=2)
    assert [a.account_name for a in report.fail] == ["two_stale"]
    assert [a.account_name for a in report.warn] == ["one_stale"]
