from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Collection

import pytest

from tests.support.books import build_book_env, insert_test_book
from tests.support.repositories import insert_repository_account
from trading.models import AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.operations.account_freshness import (
    DEFAULT_FAIL_AFTER_WEEKDAYS,
    DEFAULT_WARN_AFTER_WEEKDAYS,
    AccountFreshness,
    FreshnessReport,
    check_account_freshness,
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
    assert (report.warn, report.fail, report.never) == ((), (), ())


def test_warn_and_fail_thresholds_are_inclusive(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "one_under_warn", "2026-10-15")  # 1 weekday
    _snapshot_account(conn, "at_warn", "2026-10-14")  # 2 weekdays
    _snapshot_account(conn, "one_under_fail", "2026-10-12")  # 4 weekdays
    _snapshot_account(conn, "at_fail", "2026-10-09")  # 5 weekdays
    report = _evaluate(conn, as_of=FRIDAY)
    assert report.warn == (
        AccountFreshness("at_warn", dt.date(2026, 10, 14), 2),
        AccountFreshness("one_under_fail", dt.date(2026, 10, 12), 4),
    )
    assert report.fail == (AccountFreshness("at_fail", dt.date(2026, 10, 9), 5),)
    assert report.never == ()


def test_report_carries_last_snapshot_date_and_staleness(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "stale", "2026-10-09")
    report = _evaluate(conn, as_of=FRIDAY)
    assert report.fail == (AccountFreshness("stale", dt.date(2026, 10, 9), 5),)


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
    assert (report.warn, report.fail, report.never) == ((), (), ())


def test_snapshot_time_is_converted_to_utc_date(conn: sqlite3.Connection) -> None:
    build_book_env(conn, account_name="behind_utc", snapshot_time="2026-10-15T23:30:00-05:00")
    build_book_env(conn, account_name="ahead_of_utc", snapshot_time="2026-10-16T00:30:00+02:00")
    report = _evaluate(conn, as_of=FRIDAY, warn_after=1)
    assert report.warn == (AccountFreshness("ahead_of_utc", dt.date(2026, 10, 15), 1),)
    assert (report.fail, report.never) == ((), ())


def test_weekend_gap_does_not_count(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "friday_run", "2026-10-16")
    report = _evaluate(conn, as_of=NEXT_MONDAY)
    assert (report.warn, report.fail, report.never) == ((), (), ())


def test_account_without_snapshot_is_listed_as_never(conn: sqlite3.Connection) -> None:
    insert_repository_account(conn, name="brand_new")
    report = _evaluate(conn, as_of=FRIDAY)
    assert report.never == (AccountFreshness("brand_new", None, None),)
    assert (report.warn, report.fail) == ((), ())


def test_excluded_account_is_left_out_of_every_list(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "left_out_stale", "2026-10-02")
    insert_repository_account(conn, name="left_out_new")
    _snapshot_account(conn, "kept_stale", "2026-10-02")
    report = _evaluate(conn, as_of=FRIDAY, exclude=("left_out_stale", "left_out_new"))
    assert report.fail == (AccountFreshness("kept_stale", dt.date(2026, 10, 2), 10),)
    assert (report.warn, report.never) == ((), ())


def test_several_stale_accounts_each_appear_once(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "a_warn", "2026-10-14")
    _snapshot_account(conn, "b_fail", "2026-10-01")
    _snapshot_account(conn, "c_fail", "2026-10-05")
    insert_repository_account(conn, name="d_never")
    report = _evaluate(conn, as_of=FRIDAY)
    assert report.warn == (AccountFreshness("a_warn", dt.date(2026, 10, 14), 2),)
    assert report.fail == (
        AccountFreshness("b_fail", dt.date(2026, 10, 1), 11),
        AccountFreshness("c_fail", dt.date(2026, 10, 5), 9),
    )
    assert report.never == (AccountFreshness("d_never", None, None),)


def test_custom_thresholds(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "two_stale", "2026-10-14")
    _snapshot_account(conn, "one_stale", "2026-10-15")
    report = _evaluate(conn, as_of=FRIDAY, warn_after=1, fail_after=2)
    assert report.fail == (AccountFreshness("two_stale", dt.date(2026, 10, 14), 2),)
    assert report.warn == (AccountFreshness("one_stale", dt.date(2026, 10, 15), 1),)


def _accounts(conn: sqlite3.Connection) -> list[AccountRecord]:
    return AccountRepository(conn).fetch_all()


def test_default_thresholds_warn_at_two_weekdays_and_fail_at_five(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "one_stale", "2026-10-15")
    _snapshot_account(conn, "two_stale", "2026-10-14")
    _snapshot_account(conn, "four_stale", "2026-10-12")
    _snapshot_account(conn, "five_stale", "2026-10-09")

    report = evaluate_account_freshness(_accounts(conn), EquitySnapshotRepository(conn), as_of=FRIDAY)

    assert [(a.account_name, a.weekdays_stale) for a in report.warn] == [("four_stale", 4), ("two_stale", 2)]
    assert [(a.account_name, a.weekdays_stale) for a in report.fail] == [("five_stale", 5)]


def test_equal_thresholds_put_an_account_in_fail_only(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "two_stale", "2026-10-14")

    report = _evaluate(conn, as_of=FRIDAY, warn_after=2, fail_after=2)

    assert report.fail == (AccountFreshness("two_stale", dt.date(2026, 10, 14), 2),)
    assert report.warn == ()


def test_the_lists_keep_the_order_of_the_accounts_given(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "alpha", "2026-10-01")
    _snapshot_account(conn, "zeta", "2026-10-01")
    accounts = _accounts(conn)

    forward = evaluate_account_freshness(accounts, EquitySnapshotRepository(conn), as_of=FRIDAY)
    backward = evaluate_account_freshness(accounts[::-1], EquitySnapshotRepository(conn), as_of=FRIDAY)

    assert [a.account_name for a in forward.fail] == ["alpha", "zeta"]
    assert [a.account_name for a in backward.fail] == ["zeta", "alpha"]


def test_exclude_may_be_any_collection_of_names(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "left_out", "2026-10-02")
    _snapshot_account(conn, "kept", "2026-10-02")

    report = _evaluate(conn, as_of=FRIDAY, exclude={"left_out"})

    assert [a.account_name for a in report.fail] == ["kept"]


def test_exclude_as_a_bare_string_is_refused_not_matched_by_substring(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "prod_alt", "2026-10-02")

    with pytest.raises(TypeError, match="not a single string"):
        _evaluate(conn, as_of=FRIDAY, exclude="prod")


@pytest.mark.parametrize(("warn_after", "fail_after"), [(0, 5), (-1, 5), (3, 2), (0, 0)])
def test_thresholds_must_satisfy_one_to_warn_to_fail(
    conn: sqlite3.Connection, warn_after: int, fail_after: int
) -> None:
    with pytest.raises(ValueError, match="1 <= warn_after <= fail_after"):
        _evaluate(conn, as_of=FRIDAY, warn_after=warn_after, fail_after=fail_after)


def test_a_snapshot_dated_after_as_of_fails_the_report_naming_the_account(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "from_the_future", "2026-10-20")

    with pytest.raises(ValueError, match="from_the_future.*2026-10-20.*after as_of 2026-10-16"):
        _evaluate(conn, as_of=FRIDAY)


def test_an_unreadable_snapshot_time_fails_the_report_naming_the_account(conn: sqlite3.Connection) -> None:
    build_book_env(conn, account_name="garbled", snapshot_time="not a time")

    with pytest.raises(ValueError, match="garbled.*unreadable snapshot_time 'not a time'"):
        _evaluate(conn, as_of=FRIDAY)


def test_an_account_with_a_stopped_book_reads_as_fresh_while_another_book_snapshots(conn: sqlite3.Connection) -> None:
    env = build_book_env(conn, account_name="two_books", snapshot_time="2026-10-16T13:59:00Z")
    stopped_book = insert_test_book(conn, account_id=env.account_id, name="stopped")
    _add_snapshot(conn, stopped_book, "2026-10-01T13:59:00Z")

    report = _evaluate(conn, as_of=FRIDAY)

    assert (report.warn, report.fail, report.never) == ((), (), ())


def test_check_account_freshness_reads_every_account_in_the_database(conn: sqlite3.Connection) -> None:
    _snapshot_account(conn, "fresh", "2026-10-16")
    _snapshot_account(conn, "stale", "2026-10-09")

    report = check_account_freshness(conn, as_of=FRIDAY)

    assert [entry.account_name for entry in report.fail] == ["stale"]
