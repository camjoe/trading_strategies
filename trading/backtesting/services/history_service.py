from __future__ import annotations

import sqlite3

from trading.backtesting.repositories.history_repository import fetch_strategy_backtest_rows
from trading.coercion import coerce_float


def _safe_return_pct(starting_equity: object, ending_equity: object) -> float | None:
    start = coerce_float(starting_equity)
    end = coerce_float(ending_equity)
    if start is None or end is None:
        return None
    if start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0


def load_strategy_backtest_returns(
    conn: sqlite3.Connection,
    account_id: int,
    strategy_names: list[str],
    start_day: str,
    end_day: str,
) -> list[tuple[str, float]]:
    """Load per-run strategy returns from backtest history within a date window."""
    if not strategy_names:
        return []
    rows = fetch_strategy_backtest_rows(
        conn,
        account_id=account_id,
        strategy_names=strategy_names,
        start_day=start_day,
        end_day=end_day,
    )

    returns: list[tuple[str, float]] = []
    for row in rows:
        strategy_name = str(row["strategy_name"] or "").strip()
        if not strategy_name:
            continue

        ret = _safe_return_pct(row["starting_equity"], row["ending_equity"])
        if ret is None:
            continue

        returns.append((strategy_name, ret))

    return returns
