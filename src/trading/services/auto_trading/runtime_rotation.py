"""Rotation helpers for runtime auto-trading orchestration."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from trading.models import AccountRecord
from trading.services.market_data import MarketDataProvider
from trading.services.auto_trading.rotation import (
    compute_live_account_metrics as compute_live_account_metrics_impl,
    sync_rotation_episode as sync_rotation_episode_impl,
)
from trading.services.auto_trading.rotation_bridge import (
    RotationDeps,
    rotate_runtime_account_if_due as rotate_runtime_account_if_due_impl,
    select_account_rotation_strategy as select_account_rotation_strategy_impl,
)


def compute_runtime_live_account_metrics(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, float]:
    return compute_live_account_metrics_impl(conn, account, provider=provider)


def select_runtime_rotation_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    fetch_strategy_backtest_returns_fn: Callable[..., object],
    fetch_closed_rotation_episodes_fn: Callable[..., object],
) -> str | None:
    return select_account_rotation_strategy_impl(
        conn,
        account,
        as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns_fn,
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes_fn,
    )


def sync_runtime_rotation_episode(
    conn: sqlite3.Connection,
    account: AccountRecord,
    now_iso: str,
    *,
    fetch_open_rotation_episode_fn: Callable[..., object],
    insert_rotation_episode_fn: Callable[..., object],
    close_rotation_episode_fn: Callable[..., object],
    fetch_snapshot_count_between_fn: Callable[..., object],
    provider: MarketDataProvider | None = None,
) -> None:
    if not hasattr(conn, "execute"):
        return
    sync_rotation_episode_impl(
        conn,
        account,
        now_iso,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode_fn,
        insert_rotation_episode_fn=insert_rotation_episode_fn,
        close_rotation_episode_fn=close_rotation_episode_fn,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between_fn,
        compute_live_account_metrics_fn=lambda c, a: compute_runtime_live_account_metrics(c, a, provider=provider),
    )


def rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
    *,
    is_rotation_due_fn: Callable[..., bool],
    update_account_rotation_state_fn: Callable[..., object],
    get_account_fn: Callable[..., AccountRecord],
    fetch_strategy_backtest_returns_fn: Callable[..., object],
    fetch_closed_rotation_episodes_fn: Callable[..., object],
    fetch_open_rotation_episode_fn: Callable[..., object],
    insert_rotation_episode_fn: Callable[..., object],
    close_rotation_episode_fn: Callable[..., object],
    fetch_snapshot_count_between_fn: Callable[..., object],
    provider: MarketDataProvider | None = None,
) -> AccountRecord:
    sync_runtime_rotation_episode(
        conn,
        account,
        now_iso,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode_fn,
        insert_rotation_episode_fn=insert_rotation_episode_fn,
        close_rotation_episode_fn=close_rotation_episode_fn,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between_fn,
        provider=provider,
    )
    deps = RotationDeps(
        is_rotation_due_fn=lambda row: is_rotation_due_fn(row, as_of_iso=now_iso),
        select_optimal_strategy_fn=lambda c, a, iso: select_runtime_rotation_strategy(
            c,
            a,
            iso,
            fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns_fn,
            fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes_fn,
        ),
        update_account_rotation_state_fn=update_account_rotation_state_fn,
        get_account_fn=get_account_fn,
    )
    rotated = rotate_runtime_account_if_due_impl(conn, account_name, account, now_iso, deps)
    sync_runtime_rotation_episode(
        conn,
        rotated,
        now_iso,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode_fn,
        insert_rotation_episode_fn=insert_rotation_episode_fn,
        close_rotation_episode_fn=close_rotation_episode_fn,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between_fn,
        provider=provider,
    )
    return rotated
