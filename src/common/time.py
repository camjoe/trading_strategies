from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from common.constants import SECONDS_PER_DAY


def parse_utc_iso(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def as_utc_iso(value: datetime) -> str:
    """The canonical stored form of a timestamp: UTC, second precision, ``Z`` suffix.

    Every timestamp written to a database column must go through here (or
    :func:`utc_now_iso` / :func:`normalize_utc_iso`). Stored timestamps are
    compared as **strings** in SQL, so a column holding a mix of ``Z``,
    ``+00:00``, and bare-naive spellings of the same instant does not order or
    range-filter correctly — ``"…Z" < "…+00:00"`` is False, and a range bounded
    by a bare timestamp excludes the ``Z``-suffixed value at the same instant.
    """
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return as_utc_iso(datetime.now(timezone.utc))


def normalize_utc_iso(value: str) -> str:
    """Re-emit an ISO-8601 timestamp in the canonical stored form.

    For values arriving from outside as text — broker execution reports, imports
    — so they are stored in the same spelling as everything else. Raises
    ``ValueError`` on input that is not ISO-8601 rather than storing a string
    that would sort against the rest incorrectly.
    """
    return as_utc_iso(parse_utc_iso(value))


def next_date_str(date_str: str) -> str:
    """The calendar day after ``date_str`` (both ``YYYY-MM-DD``).

    The exclusive upper bound for "timestamps falling on ``date_str``": every
    stored timestamp that day sorts below the next day's bare date string,
    whatever timezone suffix it carries.
    """
    return (date.fromisoformat(date_str) + timedelta(days=1)).isoformat()


def utc_today() -> date:
    """Today's date in UTC.

    Persisted timestamps are stamped in UTC (``utc_now_iso``), so any date range
    bounded by one must take its other bound from UTC too. ``date.today()`` is
    local, and west of UTC it is a day behind for part of every evening — which
    silently inverts a range whose start came from a stored timestamp.
    """
    return datetime.now(timezone.utc).date()


def days_between(earlier_iso: str, later_iso: str) -> float:
    """Fractional days from ``earlier_iso`` to ``later_iso`` (negative if reversed)."""
    delta = parse_utc_iso(later_iso) - parse_utc_iso(earlier_iso)
    return delta.total_seconds() / SECONDS_PER_DAY
