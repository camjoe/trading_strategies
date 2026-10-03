from __future__ import annotations

from datetime import UTC, datetime

import pytest

from common.time import as_utc_iso, days_between, next_date_str, normalize_utc_iso, parse_utc_iso, utc_now_iso


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


class TestNormalizeUtcIso:
    @pytest.mark.parametrize(
        "spelling",
        ["2026-03-16T14:00:00Z", "2026-03-16T14:00:00+00:00", "2026-03-16T14:00:00", "2026-03-16T07:00:00-07:00"],
    )
    def test_every_spelling_of_one_instant_collapses_to_the_canonical_form(self, spelling: str) -> None:
        assert normalize_utc_iso(spelling) == "2026-03-16T14:00:00Z"

    def test_accepts_ib_basic_format_execution_time(self) -> None:
        # IB's socket API reports execution time as "YYYYMMDD HH:MM:SS", which is
        # valid basic-format ISO-8601 and parses without a bespoke reader.
        assert normalize_utc_iso("20260316 14:00:00") == "2026-03-16T14:00:00Z"

    @pytest.mark.parametrize("value", ["20260316  14:00:00", "20260316 14:00:00 US/Eastern", "not-a-timestamp"])
    def test_raises_on_unparseable_input_rather_than_storing_it(self, value: str) -> None:
        # Storing an unconverted spelling would sort against the rest of the
        # column incorrectly, so an unreadable timestamp surfaces instead.
        with pytest.raises(ValueError):
            normalize_utc_iso(value)


class TestStoredTimestampOrdering:
    """Why the canonical form matters: stored timestamps are compared as strings in SQL."""

    def test_mixed_spellings_do_not_order_or_range_correctly(self) -> None:
        zulu, offset, naive = "2026-03-16T14:00:00Z", "2026-03-16T14:00:00+00:00", "2026-03-16T14:00:00"

        # Same instant, three encodings — but string comparison disagrees.
        assert not zulu < offset
        assert naive < zulu
        # A range bounded by the naive spelling drops the Z-suffixed row at its edge.
        assert not naive <= zulu <= naive

    def test_canonical_form_removes_the_ambiguity(self) -> None:
        rendered = {normalize_utc_iso(v) for v in ("2026-03-16T14:00:00Z", "2026-03-16T14:00:00+00:00")}

        assert rendered == {"2026-03-16T14:00:00Z"}

    def test_bare_date_bound_sorts_below_every_timestamp_that_day(self) -> None:
        # The property the on-date range queries rely on.
        for spelling in ("2026-03-16T00:00:00Z", "2026-03-16T23:59:59+00:00", "2026-03-16T12:00:00"):
            assert "2026-03-16" <= spelling < next_date_str("2026-03-16")


class TestNextDateStr:
    def test_advances_one_day(self) -> None:
        assert next_date_str("2026-03-16") == "2026-03-17"

    def test_crosses_month_and_leap_year_boundaries(self) -> None:
        assert next_date_str("2026-03-31") == "2026-04-01"
        assert next_date_str("2024-02-28") == "2024-02-29"


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
