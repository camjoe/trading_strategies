from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_manage_job_schedules_args,
    manage_job_schedules as module,
)


@pytest.fixture
def _run_main_with_args(monkeypatch):
    def _run(**overrides):
        monkeypatch.setattr(module, "parse_args", lambda: make_manage_job_schedules_args(**overrides))
        return module.main()

    return _run


def test_parse_args_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["manage_job_schedules"])

    args = module.parse_args()

    assert args.config == ""
    assert args.status is False
    assert args.unregister is False
    assert args.scheduler == "auto"
    assert args.wake_system is True
    assert args.env_file == ""


def test_parse_args_reads_config_status_and_scheduler_options(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_job_schedules",
            "--config",
            "local/schedule.json",
            "--status",
            "--scheduler",
            "systemd",
            "--no-wake-system",
            "--env-file",
            "/etc/trading/.env",
        ],
    )

    args = module.parse_args()

    assert args.config == "local/schedule.json"
    assert args.status is True
    assert args.scheduler == "systemd"
    assert args.wake_system is False
    assert args.env_file == "/etc/trading/.env"


def test_default_python_prefers_venv_interpreter(monkeypatch, tmp_path) -> None:
    venv_python = tmp_path / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    monkeypatch.setattr(module.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(module.sys, "base_prefix", str(tmp_path / "base"))

    assert module._default_python() == str(venv_python)


def test_default_python_falls_back_to_sys_executable_outside_venv(monkeypatch) -> None:
    monkeypatch.setattr(module.sys, "prefix", "/same")
    monkeypatch.setattr(module.sys, "base_prefix", "/same")
    monkeypatch.setattr(module.sys, "executable", "/usr/bin/python3")

    assert module._default_python() == "/usr/bin/python3"


def test_main_unregisters_all_catalog_task_names(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_unregister(task_names, *, dry_run, scheduler_type, repo_root):
        captured["task_names"] = list(task_names)
        captured["scheduler_type"] = scheduler_type
        captured["repo_root"] = repo_root
        return 0

    monkeypatch.setattr(module, "unregister_tasks_for_platform", fake_unregister)

    assert _run_main_with_args(unregister=True, scheduler="cron") == 0
    assert captured["task_names"] == list(module.ALL_TASK_NAMES)
    assert captured["scheduler_type"] == "cron"
    assert captured["repo_root"] == tmp_path


def test_main_unregister_reports_nonzero_scheduler_code(
    monkeypatch, tmp_path: Path, _run_main_with_args, capsys
) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(module, "unregister_tasks_for_platform", lambda *args, **kwargs: 5)

    assert _run_main_with_args(unregister=True) == 5
    assert "Scheduler command returned a non-zero exit code." in capsys.readouterr().err


def test_main_entrypoint_errors_without_a_config_file(monkeypatch, tmp_path: Path, capsys) -> None:
    missing = tmp_path / "no_schedule.json"
    monkeypatch.setattr(sys, "argv", ["manage_job_schedules", "--config", str(missing)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 1
    assert "not found" in capsys.readouterr().err
