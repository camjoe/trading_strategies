"""Integration test for operational settings and the unified parameter view.

Covers the core capabilities "operational settings" and "unified parameter
source" from ``docs/overview.md``: an operator edits a global setting, and the
read-through parameter view reflects it. The test writes a runtime throttle
through the real mutation, reads it back through the settings query, and
confirms the parameter view surfaces the same value.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.services.operational_settings.mutations import set_runtime_throttle_settings
from trading.services.operational_settings.queries import fetch_runtime_throttle_settings
from trading.services.parameters.presentation import show_parameters


def test_throttle_edit_is_visible_in_the_parameter_view(conn: sqlite3.Connection) -> None:
    set_runtime_throttle_settings(
        conn,
        runtime_max_trades_per_day=7,
        runtime_max_trades_per_minute=None,
        updated_at=utc_now_iso(),
    )

    settings = fetch_runtime_throttle_settings(conn)
    assert settings.max_trades_per_day == 7

    view = show_parameters(conn)
    rendered_values = [entry.value for group in view.groups for entry in group.entries]
    assert "7" in rendered_values
