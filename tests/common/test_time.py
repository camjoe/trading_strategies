from __future__ import annotations

from datetime import datetime

from common.time import utc_now_iso


class TestUtcNowIso:
    def test_returns_utc_zulu_timestamp_without_microseconds(self) -> None:
        value = utc_now_iso()

        assert value.endswith("Z")
        assert "." not in value

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0
