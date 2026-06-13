from __future__ import annotations

import sqlite3

from trading.domain.returns import safe_return_pct
from trading.repositories.backtest_history import BacktestRunRepository


def fetch_strategy_backtest_returns(
    conn: sqlite3.Connection,
    account_id: int,
    strategy_names: list[str],
    start_day: str,
    end_day: str,
) -> list[tuple[str, float]]:
    if not strategy_names:
        return []
    rows = BacktestRunRepository(conn).fetch_by_strategy_window(
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

        ret = safe_return_pct(row["starting_equity"], row["ending_equity"])
        if ret is None:
            continue

        returns.append((strategy_name, ret))

    return returns
