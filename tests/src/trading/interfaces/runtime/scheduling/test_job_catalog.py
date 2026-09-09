from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading.interfaces.runtime.scheduling import job_catalog


def _write(tmp_path: Path, payload: dict) -> Path:
    config_path = tmp_path / "job_schedule.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def test_resolve_registers_enabled_and_unregisters_the_rest(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        {
            "jobs": [
                {"id": "daily_paper_trading", "time": "13:10"},
                {"id": "weekly_db_backup", "time": "02:00", "day_of_week": "Sunday"},
                {"id": "daily_trader_health", "time": "16:00", "enabled": False},
            ]
        },
    )

    resolution = job_catalog.resolve_schedule_config(config_path)

    registered = {spec.task_name for spec in resolution.to_register}
    assert registered == {r"Trading\DailyPaperTrading", r"Trading\WeeklyDbBackup"}
    # Disabled and absent catalog jobs are both scheduled for removal, so the host
    # matches the file after an apply.
    assert set(resolution.to_unregister) == {r"Trading\DailyTraderHealthCheck", r"Trading\DailyChallengerShadowEval"}


def test_resolve_carries_module_kind_and_args_from_catalog(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        {"jobs": [{"id": "daily_challenger_shadow_eval", "time": "12:50", "args": ["--enable-run"]}]},
    )

    spec = job_catalog.resolve_schedule_config(config_path).to_register[0]

    assert spec.module == "trading.interfaces.runtime.jobs.daily.challenger_shadow_eval"
    assert spec.schedule_kind == "daily"
    assert spec.args == ("--enable-run",)
    assert spec.log_name == "daily_challenger_shadow_eval_scheduler.log"


def test_resolve_missing_file_raises_with_copy_hint(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="job_schedule.example.json"):
        job_catalog.resolve_schedule_config(tmp_path / "absent.json")


def test_resolve_rejects_unknown_job_id(tmp_path: Path) -> None:
    config_path = _write(tmp_path, {"jobs": [{"id": "not_a_job", "time": "13:10"}]})

    with pytest.raises(ValueError, match="Unknown job id"):
        job_catalog.resolve_schedule_config(config_path)


def test_resolve_rejects_weekly_job_without_day(tmp_path: Path) -> None:
    config_path = _write(tmp_path, {"jobs": [{"id": "weekly_db_backup", "time": "02:00"}]})

    with pytest.raises(ValueError, match="day_of_week"):
        job_catalog.resolve_schedule_config(config_path)


def test_resolve_rejects_missing_time(tmp_path: Path) -> None:
    config_path = _write(tmp_path, {"jobs": [{"id": "daily_paper_trading"}]})

    with pytest.raises(ValueError, match="needs a 'time'"):
        job_catalog.resolve_schedule_config(config_path)


def test_resolve_rejects_non_string_args(tmp_path: Path) -> None:
    config_path = _write(tmp_path, {"jobs": [{"id": "daily_paper_trading", "time": "13:10", "args": [5]}]})

    with pytest.raises(ValueError, match="list of strings"):
        job_catalog.resolve_schedule_config(config_path)


def test_resolve_rejects_duplicate_job_id(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        {"jobs": [{"id": "daily_paper_trading", "time": "13:10"}, {"id": "daily_paper_trading", "time": "14:10"}]},
    )

    with pytest.raises(ValueError, match="more than once"):
        job_catalog.resolve_schedule_config(config_path)


def test_resolve_rejects_non_object_root(tmp_path: Path) -> None:
    config_path = tmp_path / "job_schedule.json"
    config_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="'jobs' array"):
        job_catalog.resolve_schedule_config(config_path)
