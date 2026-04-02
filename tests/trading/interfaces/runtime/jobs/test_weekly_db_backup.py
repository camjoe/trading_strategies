from __future__ import annotations

import datetime as dt
import importlib
from pathlib import Path


def _load():
    return importlib.import_module(
        "trading.interfaces.runtime.jobs.weekly_db_backup"
    )


class TestWeekTag:
    def test_known_date(self) -> None:
        # 2026-01-05 is ISO week 2 of 2026
        result = _load().week_tag(dt.datetime(2026, 1, 5))
        assert result == "2026_W02"

    def test_first_week(self) -> None:
        # 2026-01-01 is ISO week 1
        result = _load().week_tag(dt.datetime(2026, 1, 1))
        assert result == "2026_W01"

    def test_week_number_zero_padded(self) -> None:
        tag = _load().week_tag(dt.datetime(2026, 3, 2))
        assert "_W" in tag
        _, week_part = tag.split("_W")
        assert len(week_part) == 2  # zero-padded


class TestAlreadyCompletedThisWeek:
    def test_returns_false_when_no_logs(self, tmp_path: Path) -> None:
        module = _load()
        assert module.already_completed_this_week(tmp_path, "2026_W01") is False

    def test_returns_true_when_sentinel_present(self, tmp_path: Path) -> None:
        module = _load()
        tag = "2026_W99"
        log = tmp_path / f"weekly_db_backup_{tag}_20260101_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        module = _load()
        tag = "2026_W88"
        log = tmp_path / f"weekly_db_backup_{tag}_20260101_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is False
