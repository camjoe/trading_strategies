from __future__ import annotations

import trading.services.auto_trading.rotation as rotation_service
from tests.src.trading.services.auto_trading.factories import (
    make_auto_trading_account,
)


def _account(**overrides):
    values: dict[str, object] = {
        "id": 7,
        "rotation_schedule": '["trend","mean_reversion"]',
        "rotation_lookback_days": 30,
        "rotation_enabled": 1,
        "rotation_last_at": "2026-03-01T00:00:00Z",
        "rotation_active_strategy": "trend",
        "rotation_active_index": 0,
        "initial_cash": 1000.0,
    }
    values.update(overrides)
    return make_auto_trading_account(**values)


def test_rotate_account_if_due_uses_index_fallback_when_selected_not_in_schedule() -> None:
    account = _account(rotation_active_index=1, rotation_schedule='["trend","mean_reversion"]')
    updated_rows: list[dict[str, object]] = []
    updated = rotation_service.rotate_account_if_due(
        conn=object(),
        account_name="acct",
        account=account,
        now_iso="2026-03-31T00:00:00Z",
        is_rotation_due_fn=lambda _account: True,
        select_optimal_strategy_fn=lambda *_args, **_kwargs: "outside_schedule",
        update_account_rotation_state_fn=lambda **kwargs: updated_rows.append(kwargs),
        get_account_fn=lambda _conn, _name: account,
    )
    assert updated is account
    assert updated_rows[0]["rotation_active_index"] == 1
