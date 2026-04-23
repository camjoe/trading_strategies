"""Auto-trading rotation bridge helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from trading.domain.rotation import resolve_rotation_mode
from trading.models import AccountRecord


def select_account_rotation_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    select_optimal_strategy_impl_fn: Callable[..., str | None],
    select_regime_strategy_impl_fn: Callable[..., str | None] | None,
    fetch_strategy_backtest_returns_fn: Callable[..., list[tuple[str, float]]],
    fetch_policy_features_fn: Callable[[str], object] | None,
    fetch_news_features_fn: Callable[[str], object] | None = None,
    fetch_social_features_fn: Callable[[str], object] | None = None,
    fetch_rotation_overlay_tickers_fn: Callable[[sqlite3.Connection, AccountRecord], list[str]] | None = None,
    fetch_closed_rotation_episodes_fn: Callable[..., list[sqlite3.Row]] | None = None,
) -> str | None:
    if resolve_rotation_mode(account) == "regime":
        if select_regime_strategy_impl_fn is None or fetch_policy_features_fn is None:
            return None
        return select_regime_strategy_impl_fn(
            account,
            conn=conn,
            fetch_policy_features_fn=fetch_policy_features_fn,
            fetch_news_features_fn=fetch_news_features_fn,
            fetch_social_features_fn=fetch_social_features_fn,
            fetch_rotation_overlay_tickers_fn=fetch_rotation_overlay_tickers_fn,
        )

    return select_optimal_strategy_impl_fn(
        conn,
        account,
        as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns_fn,
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes_fn,
    )


@dataclass
class RotationDeps:
    rotate_account_if_due_impl_fn: Callable[..., AccountRecord]
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
    return deps.rotate_account_if_due_impl_fn(
        conn,
        account_name,
        account,
        now_iso,
        is_rotation_due_fn=deps.is_rotation_due_fn,
        select_optimal_strategy_fn=deps.select_optimal_strategy_fn,
        update_account_rotation_state_fn=deps.update_account_rotation_state_fn,
        get_account_fn=deps.get_account_fn,
    )
