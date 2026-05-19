from __future__ import annotations

import sys

from tests.trading.interfaces.runtime.jobs.helpers import check_daily_trader_health as module


def run_main(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["check_daily_trader_health"] + argv)
    return module.main()


def test_max_age_hours_zero_returns_2(monkeypatch) -> None:
    assert run_main(monkeypatch, ["--max-age-hours", "0", "--repo-root", "."]) == 2


def test_max_age_hours_negative_returns_2(monkeypatch) -> None:
    assert run_main(monkeypatch, ["--max-age-hours", "-1", "--repo-root", "."]) == 2
