from __future__ import annotations

from datetime import UTC, date, datetime, timezone

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
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return as_utc_iso(datetime.now(timezone.utc))


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
