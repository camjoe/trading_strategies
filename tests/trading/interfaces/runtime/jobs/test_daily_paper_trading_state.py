from __future__ import annotations

import datetime as dt
from pathlib import Path

from tests.support import load_runtime_job

MODULE_NAME = "trading.interfaces.runtime.jobs.daily_paper_trading"


def _load():
    return load_runtime_job(MODULE_NAME)


class TestAlreadyCompletedToday:
    def test_returns_false_when_no_logs(self, tmp_path: Path) -> None:
        assert _load().already_completed_today(tmp_path, today=dt.date(2026, 3, 30)) is False

    def test_returns_true_when_sentinel_found(self, tmp_path: Path) -> None:
        module = _load()
        today = dt.date(2026, 3, 30)
        log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_120000.log"
        log.write_text(f"run\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_today(tmp_path, today=today) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        module = _load()
        today = dt.date(2026, 3, 30)
        log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_120000.log"
        log.write_text("partial run\n", encoding="utf-8")
        assert module.already_completed_today(tmp_path, today=today) is False

    def test_uses_todays_date_tag_by_default(self, tmp_path: Path) -> None:
        module = _load()
        today = dt.date.today()
        log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_000000.log"
        log.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_today(tmp_path) is True


class TestGroupAccountsByCaps:
    def test_single_group(self) -> None:
        caps = {"a": (1, 5), "b": (1, 5)}
        result = _load().group_accounts_by_caps(["a", "b"], caps)
        assert result == {(1, 5): ["a", "b"]}

    def test_multiple_groups(self) -> None:
        caps = {"a": (1, 5), "b": (1, 11), "c": (1, 5)}
        result = _load().group_accounts_by_caps(["a", "b", "c"], caps)
        assert result[(1, 5)] == ["a", "c"]
        assert result[(1, 11)] == ["b"]

    def test_preserves_insertion_order_within_group(self) -> None:
        caps = {"z": (1, 5), "a": (1, 5), "m": (1, 5)}
        result = _load().group_accounts_by_caps(["z", "a", "m"], caps)
        assert result[(1, 5)] == ["z", "a", "m"]

    def test_empty_accounts_returns_empty(self) -> None:
        assert _load().group_accounts_by_caps([], {}) == {}
