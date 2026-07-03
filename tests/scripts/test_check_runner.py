from __future__ import annotations

from scripts.checks._runner import CheckStep, run_check_steps


def test_run_check_steps_stops_on_first_failure() -> None:
    calls: list[str] = []

    result = run_check_steps(
        [
            CheckStep("first", lambda: calls.append("first") or 0),
            CheckStep("second", lambda: calls.append("second") or 3),
            CheckStep("third", lambda: calls.append("third") or 0),
        ]
    )

    assert result == 3
    assert calls == ["first", "second"]


def test_run_check_steps_skips_marked_steps() -> None:
    calls: list[str] = []

    result = run_check_steps(
        [
            CheckStep("skip me", lambda: calls.append("skip me") or 1, skip=True),
            CheckStep("run me", lambda: calls.append("run me") or None),
        ]
    )

    assert result == 0
    assert calls == ["run me"]
