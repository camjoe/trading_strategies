"""Tests for trading.services.operational_settings.show_global_settings_history."""

from __future__ import annotations

import sqlite3

import pytest

from trading.services.operational_settings import set_runtime_throttle_settings, show_global_settings_history


def test_prints_no_changes_message_when_empty(
    conn: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events = show_global_settings_history(conn)

    assert events == []
    assert "No global settings changes recorded." in capsys.readouterr().out


def test_prints_recorded_changes(
    conn: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_runtime_throttle_settings(
        conn,
        runtime_max_trades_per_day=5,
        runtime_max_trades_per_minute=2,
        updated_at="2026-07-26T00:00:00Z",
    )

    events = show_global_settings_history(conn)

    out = capsys.readouterr().out
    assert len(events) == 1
    assert "Global settings change history" in out
    assert "throttle" in out
    assert "runtime_max_trades_per_day: None -> 5" in out
