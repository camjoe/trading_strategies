"""Rotation helpers for runtime auto-trading orchestration."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from trading.models import AccountRecord
from trading.services.auto_trading.rotation_bridge import (
    RotationDeps,
    rotate_runtime_account_if_due as rotate_runtime_account_if_due_impl,
    select_account_rotation_strategy as select_account_rotation_strategy_impl,
)


def select_runtime_rotation_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
) -> str | None:
    return select_account_rotation_strategy_impl(conn, account, as_of_iso)


def rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
    *,
    is_rotation_due_fn: Callable[..., bool],
    update_account_rotation_state_fn: Callable[..., object],
    get_account_fn: Callable[..., AccountRecord],
) -> AccountRecord:
    deps = RotationDeps(
        is_rotation_due_fn=lambda row: is_rotation_due_fn(row, as_of_iso=now_iso),
        select_optimal_strategy_fn=lambda c, a, iso: select_runtime_rotation_strategy(c, a, iso),
        update_account_rotation_state_fn=update_account_rotation_state_fn,
        get_account_fn=get_account_fn,
    )
    return rotate_runtime_account_if_due_impl(conn, account_name, account, now_iso, deps)
