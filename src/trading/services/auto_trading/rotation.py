"""Rotation helpers used by runtime auto-trading orchestration."""

from __future__ import annotations

import sqlite3
from typing import Callable, cast

from common.coercion import row_expect_int
from trading.domain.rotation import (
    parse_rotation_schedule,
    resolve_active_strategy,
)
from trading.models import AccountRecord


def rotate_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
    *,
    is_rotation_due_fn: Callable[[AccountRecord], bool],
    select_optimal_strategy_fn: Callable[[sqlite3.Connection, AccountRecord, str], str | None],
    update_account_rotation_state_fn: Callable[..., None],
    get_account_fn: Callable[[sqlite3.Connection, str], AccountRecord],
) -> AccountRecord:
    if not is_rotation_due_fn(account):
        return account

    # Round-robin "time" mode is retired: rotation selection is always the
    # decision-score champion/challenger model (select_optimal_strategy_fn routes
    # through it). is_rotation_due is the cadence trigger; the cooldown guard inside
    # the selection prevents churn.
    selected = select_optimal_strategy_fn(conn, account, now_iso)
    active = selected or resolve_active_strategy(account)
    schedule = parse_rotation_schedule(account["rotation_schedule"])
    if schedule and active in schedule:
        active_idx = schedule.index(active)
    else:
        active_idx = int(cast(int | float | str | bytes | bytearray, account["rotation_active_index"] or 0))

    update_account_rotation_state_fn(
        account_id=row_expect_int(account, "id"),
        strategy=active,
        rotation_active_index=active_idx,
        rotation_active_strategy=active,
        rotation_last_at=now_iso,
    )
    return get_account_fn(conn, account_name)
