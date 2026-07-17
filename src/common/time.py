from __future__ import annotations

from datetime import UTC, datetime, timezone


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


def days_between(earlier_iso: str, later_iso: str) -> float:
    """Fractional days from ``earlier_iso`` to ``later_iso`` (negative if reversed)."""
    delta = parse_utc_iso(later_iso) - parse_utc_iso(earlier_iso)
    return delta.total_seconds() / 86400.0
