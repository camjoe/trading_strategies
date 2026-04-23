from __future__ import annotations

from datetime import UTC, datetime

from common.time import parse_utc_iso, utc_now_iso


class TestUtcNowIso:
    def test_returns_utc_zulu_timestamp_without_microseconds(self) -> None:
        value = utc_now_iso()

        assert value.endswith("Z")
        assert "." not in value

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0


class TestParseUtcIso:
    def test_accepts_zulu_suffix(self) -> None:
        parsed = parse_utc_iso("2026-03-16T14:00:00Z")

        assert parsed == datetime(2026, 3, 16, 14, 0, tzinfo=UTC)

    def test_normalizes_offset_to_utc(self) -> None:
        parsed = parse_utc_iso("2026-03-16T07:00:00-07:00")

        assert parsed == datetime(2026, 3, 16, 14, 0, tzinfo=UTC)

    def test_assumes_naive_timestamp_is_utc(self) -> None:
        parsed = parse_utc_iso("2026-03-16T14:00:00")

        assert parsed == datetime(2026, 3, 16, 14, 0, tzinfo=UTC)
