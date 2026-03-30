from __future__ import annotations

import importlib

import pytest


def _load():
    return importlib.import_module(
        "trading.interfaces.runtime.jobs.register_weekly_backup"
    )


# ---------------------------------------------------------------------------
# validate_day
# ---------------------------------------------------------------------------

class TestValidateDay:
    @pytest.mark.parametrize(
        ("input_day", "expected_key"),
        [
            ("Saturday", "saturday"),
            ("SUNDAY", "sunday"),
            ("monday", "monday"),
            ("  Friday  ", "friday"),
        ],
    )
    def test_valid_days(self, input_day: str, expected_key: str) -> None:
        assert _load().validate_day(input_day) == expected_key

    def test_invalid_day_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid day"):
            _load().validate_day("Funday")


# ---------------------------------------------------------------------------
# validate_time
# ---------------------------------------------------------------------------

class TestValidateTime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("00:00", (0, 0)),
            ("02:30", (2, 30)),
            ("23:59", (23, 59)),
        ],
    )
    def test_valid_times(self, value: str, expected: tuple[int, int]) -> None:
        assert _load().validate_time(value) == expected

    def test_missing_colon_raises(self) -> None:
        with pytest.raises(ValueError, match="HH:MM"):
            _load().validate_time("0230")

    def test_hour_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="24-hour"):
            _load().validate_time("25:00")

    def test_minute_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="24-hour"):
            _load().validate_time("12:60")


# ---------------------------------------------------------------------------
# windows_register / windows_unregister (dry-run only — no subprocess)
# ---------------------------------------------------------------------------

class TestWindowsDryRun:
    def _make_args(self, *, unregister: bool = False):
        import types
        return types.SimpleNamespace(
            day_of_week="Sunday",
            time="02:00",
            task_name="TradingStrategies_WeeklyDbBackup",
            dry_run=True,
            unregister=unregister,
            python="python",
        )

    def test_windows_register_dry_run_prints_and_returns_0(self, capsys) -> None:
        module = _load()
        code = module.windows_register(self._make_args())
        assert code == 0
        assert "DRY RUN" in capsys.readouterr().out

    def test_windows_unregister_dry_run_prints_and_returns_0(self, capsys) -> None:
        module = _load()
        code = module.windows_unregister(self._make_args(unregister=True))
        assert code == 0
        assert "DRY RUN" in capsys.readouterr().out
