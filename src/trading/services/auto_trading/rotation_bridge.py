"""Auto-trading rotation bridge helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from trading.models import AccountRecord
from trading.services.auto_trading.book_rotation import evaluate_account_rotation_decision
from trading.services.auto_trading.rotation import (
    rotate_account_if_due as rotate_account_if_due_impl,
)


def select_account_rotation_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
) -> str | None:
    # Selection runs the decision-score champion/challenger model on the account's
    # default book, writing rotation_decisions.
    return evaluate_account_rotation_decision(conn, account, as_of_iso)


@dataclass
class RotationDeps:
    is_rotation_due_fn: Callable[[AccountRecord], bool]
    select_optimal_strategy_fn: Callable[[sqlite3.Connection, AccountRecord, str], str | None]
    update_account_rotation_state_fn: Callable[..., None]
    get_account_fn: Callable[[sqlite3.Connection, str], AccountRecord]


def rotate_runtime_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
    deps: RotationDeps,
) -> AccountRecord:
    return rotate_account_if_due_impl(
        conn,
        account_name,
        account,
        now_iso,
        is_rotation_due_fn=deps.is_rotation_due_fn,
        select_optimal_strategy_fn=deps.select_optimal_strategy_fn,
        update_account_rotation_state_fn=deps.update_account_rotation_state_fn,
        get_account_fn=deps.get_account_fn,
    )
