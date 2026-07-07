"""Rotation helpers used by runtime auto-trading orchestration."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Callable, cast

from common.coercion import row_expect_int, row_float, row_int
from common.time import parse_utc_iso
from trading.domain.accounting import compute_account_state
from trading.domain.returns import safe_return_pct
from trading.domain.rotation import (
    next_rotation_state,
    parse_rotation_schedule,
    resolve_active_strategy,
    resolve_optimality_mode,
    resolve_rotation_mode,
)
from trading.models import AccountRecord
from trading.services.accounting import list_account_trades
from trading.services.market_data import MarketDataProvider
from trading.services.reporting import compute_market_value_and_unrealized, fetch_latest_prices

# Minimum completed live episodes required before the live component receives
# its full configured weight in hybrid rotation scoring.
MIN_LIVE_EPISODES_FOR_FULL_CONFIDENCE = 3

# Baseline hybrid score weighting: mostly backtest-driven until live evidence
# accumulates, with a smaller live overlay once strategy episodes are observed.
HYBRID_BACKTEST_WEIGHT = 0.70
HYBRID_LIVE_WEIGHT = 0.30


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


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


def select_optimal_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    fetch_strategy_backtest_returns_fn: Callable[..., list[tuple[str, float]]],
    fetch_closed_rotation_episodes_fn: Callable[..., list[sqlite3.Row]] | None = None,
) -> str | None:
    schedule = parse_rotation_schedule(account["rotation_schedule"])
    if not schedule:
        return None

    lookback_days = row_int(account, "rotation_lookback_days") or 180
    as_of_dt = parse_utc_iso(as_of_iso)
    end_day = as_of_dt.date().isoformat()
    start_day = (as_of_dt - timedelta(days=lookback_days)).date().isoformat()

    returns = fetch_strategy_backtest_returns_fn(
        conn,
        account_id=row_expect_int(account, "id"),
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
        by_strategy = {}

    optimality_mode = resolve_optimality_mode(account)
    scores: dict[str, float] = {}
    if optimality_mode == "hybrid_weighted":
        live_scores: dict[str, list[float]] = {}
        if fetch_closed_rotation_episodes_fn is not None:
            closed_rows = fetch_closed_rotation_episodes_fn(
                account_id=row_expect_int(account, "id"),
                strategy_names=schedule,
                start_iso=f"{start_day}T00:00:00Z",
                end_iso=as_of_iso,
            )
            for row in closed_rows:
                starting_equity = row["starting_equity"]
                ending_equity = row["ending_equity"]
                if starting_equity is None or ending_equity is None:
                    continue
                live_return = safe_return_pct(starting_equity, ending_equity)
                if live_return is None:
                    continue
                live_scores.setdefault(str(row["strategy_name"]), []).append(float(live_return))

        for strategy_name in schedule:
            backtest_score = _average(by_strategy.get(strategy_name, []))
            live_values = live_scores.get(strategy_name, [])
            live_score = _average(live_values)
            if backtest_score is None and live_score is None:
                continue
            if backtest_score is None:
                assert live_score is not None
                scores[strategy_name] = float(live_score)
                continue
            if live_score is None:
                scores[strategy_name] = float(backtest_score)
                continue
            live_confidence = min(len(live_values) / MIN_LIVE_EPISODES_FOR_FULL_CONFIDENCE, 1.0)
            live_weight = HYBRID_LIVE_WEIGHT * live_confidence
            backtest_weight = HYBRID_BACKTEST_WEIGHT + (HYBRID_LIVE_WEIGHT - live_weight)
            scores[strategy_name] = (float(backtest_score) * backtest_weight) + (float(live_score) * live_weight)
    elif optimality_mode == "average_return":
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
