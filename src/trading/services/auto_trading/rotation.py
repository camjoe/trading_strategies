"""Rotation helpers used by runtime auto-trading orchestration."""

from __future__ import annotations

import sqlite3
from typing import Callable, cast

from common.coercion import row_expect_int, row_float
from trading.domain.accounting import compute_account_state
from trading.domain.rotation import (
    next_rotation_state,
    parse_rotation_schedule,
    resolve_active_strategy,
    resolve_rotation_mode,
)
from trading.models import AccountRecord
from trading.services.accounting import list_account_trades
from trading.services.market_data import MarketDataProvider
from trading.services.reporting import compute_market_value_and_unrealized, fetch_latest_prices


def compute_live_account_metrics(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, float]:
    state = cast(
        object,
        compute_account_state(
            row_float(account, "initial_cash") or 0.0,
            list_account_trades(conn, row_expect_int(account, "id")),
        ),
    )
    positions = cast(dict[str, float], getattr(state, "positions"))
    avg_cost = cast(dict[str, float], getattr(state, "avg_cost"))
    prices = fetch_latest_prices(sorted(positions.keys()), provider=provider) if positions else {}
    market_value, _unrealized = compute_market_value_and_unrealized(positions, avg_cost, prices)
    equity = float(getattr(state, "cash", 0.0)) + float(market_value)
    return {
        "equity": equity,
        "realized_pnl": float(getattr(state, "realized_pnl", 0.0)),
    }


def sync_rotation_episode(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    fetch_open_rotation_episode_fn: Callable[..., sqlite3.Row | None],
    insert_rotation_episode_fn: Callable[..., None],
    close_rotation_episode_fn: Callable[..., None],
    fetch_snapshot_count_between_fn: Callable[..., int],
    compute_live_account_metrics_fn: Callable[[sqlite3.Connection, AccountRecord], dict[str, float]],
) -> None:
    rotation_enabled = bool(int(cast(int | float | str | bytes | bytearray, account["rotation_enabled"] or 0)))
    if not rotation_enabled:
        return

    active_strategy = resolve_active_strategy(account)
    if not active_strategy:
        return

    metrics = compute_live_account_metrics_fn(conn, account)
    open_episode = fetch_open_rotation_episode_fn(account_id=row_expect_int(account, "id"))
    episode_started_at = str(account["rotation_last_at"] or as_of_iso)

    if open_episode is None:
        insert_rotation_episode_fn(
            account_id=row_expect_int(account, "id"),
            strategy_name=active_strategy,
            started_at=episode_started_at,
            starting_equity=float(metrics["equity"]),
            starting_realized_pnl=float(metrics["realized_pnl"]),
        )
        return

    if str(open_episode["strategy_name"]) == active_strategy:
        return

    snapshot_count = fetch_snapshot_count_between_fn(
        account_id=row_expect_int(account, "id"),
        start_iso=str(open_episode["started_at"]),
        end_iso=as_of_iso,
    )
    starting_realized_pnl = float(open_episode["starting_realized_pnl"])
    close_rotation_episode_fn(
        episode_id=int(open_episode["id"]),
        ended_at=as_of_iso,
        ending_equity=float(metrics["equity"]),
        ending_realized_pnl=float(metrics["realized_pnl"]),
        realized_pnl_delta=float(metrics["realized_pnl"]) - starting_realized_pnl,
        snapshot_count=snapshot_count,
    )
    insert_rotation_episode_fn(
        account_id=row_expect_int(account, "id"),
        strategy_name=active_strategy,
        started_at=as_of_iso,
        starting_equity=float(metrics["equity"]),
        starting_realized_pnl=float(metrics["realized_pnl"]),
    )


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

    rotation_mode = resolve_rotation_mode(account)
    if rotation_mode in {"optimal", "regime"}:
        selected = select_optimal_strategy_fn(conn, account, now_iso)
        active = selected or resolve_active_strategy(account)
        schedule = parse_rotation_schedule(account["rotation_schedule"])
        if schedule and active in schedule:
            active_idx = schedule.index(active)
        else:
            active_idx = int(cast(int | float | str | bytes | bytearray, account["rotation_active_index"] or 0))
        next_state = {
            "rotation_active_index": active_idx,
            "rotation_active_strategy": active,
            "rotation_last_at": now_iso,
        }
    else:
        next_state = next_rotation_state(account, as_of_iso=now_iso)

    update_account_rotation_state_fn(
        account_id=row_expect_int(account, "id"),
        strategy=str(next_state["rotation_active_strategy"]),
        rotation_active_index=int(cast(int | float | str | bytes | bytearray, next_state["rotation_active_index"])),
        rotation_active_strategy=str(next_state["rotation_active_strategy"]),
        rotation_last_at=str(next_state["rotation_last_at"]),
    )
    return get_account_fn(conn, account_name)
