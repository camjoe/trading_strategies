from __future__ import annotations

from types import SimpleNamespace

from trading.interfaces.runtime.jobs import scheduler_installer


def test_unregister_tasks_for_platform_windows_attempts_all_deletes(monkeypatch) -> None:
    commands: list[list[str]] = []
    results = iter([1, 0])

    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Windows")

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=next(results))

    monkeypatch.setattr(scheduler_installer.subprocess, "run", fake_run)

    exit_code = scheduler_installer.unregister_tasks_for_platform(
        [r"Trading\MissingTask", r"Trading\ExistingTask"],
        dry_run=False,
    )

    assert commands == [
        ["schtasks", "/Delete", "/TN", r"Trading\MissingTask", "/F"],
        ["schtasks", "/Delete", "/TN", r"Trading\ExistingTask", "/F"],
    ]
    assert exit_code == 1
