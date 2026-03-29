from __future__ import annotations

import sqlite3
from typing import Callable

from trading.models import AccountState


def compute_market_value_and_unrealized(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> tuple[float, float]:
    market_value = 0.0
    unrealized = 0.0
    for ticker, qty in positions.items():
        price = prices.get(ticker)
        if price is None:
            continue
        market_value += qty * price
        unrealized += (price - avg_cost[ticker]) * qty
    return market_value, unrealized


def strategy_return_pct(equity: float, initial_cash: float) -> float:
    return ((equity / initial_cash) - 1.0) * 100.0


def benchmark_available(benchmark_equity: float | None, benchmark_return_pct: float | None) -> bool:
    return benchmark_equity is not None and benchmark_return_pct is not None


def alpha_pct(strategy_return_pct_value: float, benchmark_return_pct_value: float) -> float:
    return strategy_return_pct_value - benchmark_return_pct_value


def positions_summary_text(positions: dict[str, float]) -> tuple[int, str]:
    position_count = len(positions)
    if not positions:
        return position_count, "none"

    sorted_positions = sorted(positions.items(), key=lambda x: x[0])
    positions_text = ", ".join([f"{ticker}:{qty:.2f}" for ticker, qty in sorted_positions[:5]])
    if len(sorted_positions) > 5:
        positions_text += ", ..."
    return position_count, positions_text


def build_account_stats(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    *,
    load_trades_fn: Callable[[sqlite3.Connection, int], list[sqlite3.Row]],
    compute_account_state_fn: Callable[[float, list[sqlite3.Row]], AccountState],
    fetch_latest_prices_fn: Callable[[list[str]], dict[str, float]],
    row_expect_int_fn: Callable[[sqlite3.Row, str], int],
    row_expect_float_fn: Callable[[sqlite3.Row, str], float],
) -> tuple[AccountState, dict[str, float], float, float, float]:
    account_id = row_expect_int_fn(account, "id")
    initial_cash = row_expect_float_fn(account, "initial_cash")
    trades = load_trades_fn(conn, account_id)
    state = compute_account_state_fn(initial_cash, trades)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices_fn(tickers) if tickers else {}

    market_value, unrealized = compute_market_value_and_unrealized(state.positions, state.avg_cost, prices)
    equity = state.cash + market_value
    return state, prices, market_value, unrealized, equity


def infer_overall_trend(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
    *,
    fetch_recent_equity_rows_fn: Callable[..., list[sqlite3.Row]],
    row_float_fn: Callable[[sqlite3.Row, str], float | None],
) -> str:
    rows = fetch_recent_equity_rows_fn(
        conn,
        account_id=account_id,
        limit=int(max(lookback, 2)),
    )

    history: list[float] = [h for h in (row_float_fn(r, "equity") for r in rows) if h is not None]
    history.reverse()
    history.append(current_equity)

    if len(history) < 3:
        return "insufficient-data"

    first = history[0]
    last = history[-1]
    if first == 0:
        return "insufficient-data"

    move_pct = ((last - first) / first) * 100.0
    if move_pct > 1.0:
        return "up"
    if move_pct < -1.0:
        return "down"
    return "flat"