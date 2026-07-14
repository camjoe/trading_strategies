from __future__ import annotations

from datetime import UTC, datetime

from common.time import as_utc_iso, days_between, parse_utc_iso, utc_now_iso


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


class TestAsUtcIso:
    def test_renders_zulu_without_microseconds(self) -> None:
        rendered = as_utc_iso(datetime(2026, 3, 16, 14, 0, 0, 123456, tzinfo=UTC))

        assert rendered == "2026-03-16T14:00:00Z"


class TestDaysBetween:
    def test_whole_day_gap(self) -> None:
        assert days_between("2026-03-16T00:00:00Z", "2026-03-19T00:00:00Z") == 3.0

    def test_same_instant_is_zero(self) -> None:
        assert days_between("2026-03-16T12:00:00Z", "2026-03-16T12:00:00Z") == 0.0

    def test_sub_day_fraction(self) -> None:
        assert days_between("2026-03-16T00:00:00Z", "2026-03-16T12:00:00Z") == 0.5

    def test_reversed_order_is_negative(self) -> None:
        assert days_between("2026-03-19T00:00:00Z", "2026-03-16T00:00:00Z") == -3.0

    def test_mixed_offsets_normalize(self) -> None:
        # 00:00-07:00 is 07:00Z; to 07:00Z the same day is zero elapsed.
        assert days_between("2026-03-16T00:00:00-07:00", "2026-03-16T07:00:00Z") == 0.0
