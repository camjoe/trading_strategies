from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Callable, cast

from trading.domain.returns import safe_return_pct as safe_return_pct_impl


def parse_as_of_iso(as_of_iso: str) -> datetime:
    text = as_of_iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def safe_return_pct(
    starting_equity: object,
    ending_equity: object,
    *,
    coerce_float_fn: Callable[[object], float | None],
) -> float | None:
    return safe_return_pct_impl(
        starting_equity,
        ending_equity,
        coerce_float_fn=coerce_float_fn,
    )


def select_optimal_strategy(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
    *,
    parse_rotation_schedule_fn: Callable[[object | None], list[str]],
    parse_as_of_iso_fn: Callable[[str], datetime],
    fetch_strategy_backtest_returns_fn: Callable[..., list[tuple[str, float]]],
    resolve_optimality_mode_fn: Callable[[sqlite3.Row], str],
) -> str | None:
    schedule = parse_rotation_schedule_fn(account["rotation_schedule"])
    if not schedule:
        return None

    lookback_days = int(account["rotation_lookback_days"] or 180)
    as_of_dt = parse_as_of_iso_fn(as_of_iso)
    end_day = as_of_dt.date().isoformat()
    start_day = (as_of_dt - timedelta(days=lookback_days)).date().isoformat()

    returns = fetch_strategy_backtest_returns_fn(
        conn,
        account_id=int(account["id"]),
        strategy_names=schedule,
        start_day=start_day,
        end_day=end_day,
    )

    if not returns:
        return None

    by_strategy: dict[str, list[float]] = {}
    latest_by_strategy: dict[str, float] = {}
    for strategy_name, ret in returns:
        by_strategy.setdefault(strategy_name, []).append(ret)
        if strategy_name not in latest_by_strategy:
            latest_by_strategy[strategy_name] = ret

    if not by_strategy:
        return None

    optimality_mode = resolve_optimality_mode_fn(account)
    scores: dict[str, float] = {}
    if optimality_mode == "average_return":
        for strategy_name, values in by_strategy.items():
            scores[strategy_name] = sum(values) / len(values)
    else:
        scores = dict(latest_by_strategy)

    if not scores:
        return None

    best_strategy = max(scores.items(), key=lambda item: item[1])[0]
    return best_strategy if best_strategy in schedule else None


def rotate_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
    *,
    is_rotation_due_fn: Callable[[sqlite3.Row], bool],
    resolve_rotation_mode_fn: Callable[[sqlite3.Row], str],
    select_optimal_strategy_fn: Callable[[sqlite3.Connection, sqlite3.Row, str], str | None],
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str],
    parse_rotation_schedule_fn: Callable[[object | None], list[str]],
    next_rotation_state_fn: Callable[[sqlite3.Row, str], dict[str, object]],
    update_account_rotation_state_fn: Callable[..., None],
    get_account_fn: Callable[[sqlite3.Connection, str], sqlite3.Row],
) -> sqlite3.Row:
    if not is_rotation_due_fn(account):
        return account

    rotation_mode = resolve_rotation_mode_fn(account)
    if rotation_mode == "optimal":
        optimal = select_optimal_strategy_fn(conn, account, now_iso)
        active = optimal or resolve_active_strategy_fn(account)
        schedule = parse_rotation_schedule_fn(account["rotation_schedule"])
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
        next_state = next_rotation_state_fn(account, now_iso)

    update_account_rotation_state_fn(
        conn,
        account_id=int(account["id"]),
        strategy=str(next_state["rotation_active_strategy"]),
        rotation_active_index=int(
            cast(int | float | str | bytes | bytearray, next_state["rotation_active_index"])
        ),
        rotation_active_strategy=str(next_state["rotation_active_strategy"]),
        rotation_last_at=str(next_state["rotation_last_at"]),
    )
    return get_account_fn(conn, account_name)
