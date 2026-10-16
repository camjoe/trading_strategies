"""Names every account whose newest equity snapshot is too many weekdays old.

Every daily run snapshots each account it handles, market open or not, so an
account that was skipped, never reached, aborted, or dropped by a typo stops
getting snapshots. This service only reads; it opens no connection and writes
nothing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from common.time import parse_utc_iso
from trading.models import AccountRecord
from trading.repositories.snapshots import EquitySnapshotRepository

# Weekdays without a snapshot before an account is reported as a warning.
DEFAULT_WARN_AFTER_WEEKDAYS = 2

# Weekdays without a snapshot before an account is reported as a failure.
DEFAULT_FAIL_AFTER_WEEKDAYS = 5

# Python's date.weekday() numbers Monday as 0; Saturday (5) and Sunday (6) are not weekdays.
_FIRST_WEEKEND_WEEKDAY = 5


@dataclass(frozen=True)
class AccountFreshness:
    """One account's newest snapshot date and how many weekdays old it is."""

    account_name: str
    last_snapshot_date: dt.date | None
    weekdays_stale: int | None


@dataclass(frozen=True)
class FreshnessReport:
    """Accounts grouped by staleness. ``never`` holds accounts with no snapshot yet."""

    warn: list[AccountFreshness]
    fail: list[AccountFreshness]
    never: list[AccountFreshness]


def weekdays_since(last: dt.date, as_of: dt.date) -> int:
    """Count Monday-to-Friday dates ``d`` with ``last < d <= as_of``.

    Market holidays count as weekdays: the daily job runs Monday to Friday
    regardless. A ``last`` after ``as_of`` counts as 0.
    """
    elapsed_days = (as_of - last).days
    return sum(
        1
        for offset in range(1, elapsed_days + 1)
        if (last + dt.timedelta(days=offset)).weekday() < _FIRST_WEEKEND_WEEKDAY
    )


def evaluate_account_freshness(
    accounts: Iterable[AccountRecord],
    snapshots: EquitySnapshotRepository,
    *,
    as_of: dt.date,
    warn_after: int = DEFAULT_WARN_AFTER_WEEKDAYS,
    fail_after: int = DEFAULT_FAIL_AFTER_WEEKDAYS,
    exclude: Collection[str] = (),
) -> FreshnessReport:
    """Sort accounts into warn, fail, and never-snapshotted lists as of ``as_of``.

    The snapshot date is the UTC date of the newest ``snapshot_time``. Accounts
    named in ``exclude`` appear in no list.
    """
    warn: list[AccountFreshness] = []
    fail: list[AccountFreshness] = []
    never: list[AccountFreshness] = []
    for account in accounts:
        if account.name in exclude:
            continue
        latest = snapshots.fetch_latest(account_id=account.id)
        if latest is None:
            never.append(AccountFreshness(account.name, None, None))
            continue
        last_date = parse_utc_iso(latest.snapshot_time).date()
        stale = weekdays_since(last_date, as_of)
        entry = AccountFreshness(account.name, last_date, stale)
        if stale >= fail_after:
            fail.append(entry)
        elif stale >= warn_after:
            warn.append(entry)
    return FreshnessReport(warn=warn, fail=fail, never=never)
