from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from backtesting.domain.simulation_math import update_on_buy, update_on_sell
from common.coercion import row_float
from common.constants import ANNUALIZATION_FACTOR, TRADING_DAYS_PER_YEAR

# Scale factor for converting decimal returns into operator-facing percentage values.
PERCENT_SCALE = 100.0

# Minimum equity observations needed to compute a return series.
MIN_RETURN_OBSERVATIONS = 2


@dataclass(frozen=True)
class BacktestPerformanceMetrics:
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    avg_trade_return_pct: float | None = None


def equity_curve_from_rows(snapshot_rows: Sequence[Mapping[str, object]]) -> list[float]:
    """The equity marks from *snapshot_rows*, in row order, skipping unset ones.

    A snapshot with a null ``equity`` carries no mark to plot or measure; dropping
    it keeps the curve a series of real values rather than one holding ``None``,
    which every metric here would have to re-filter.
    """
    return [value for value in (row_float(row, "equity") for row in snapshot_rows) if value is not None]


def total_return_pct(*, first_equity: float, last_equity: float) -> float:
    """Total return across an interval, from its first and last equity marks (percent).

    The one definition of total return: a standalone run, a leaderboard row, and an
    optimizer window all measure it here, so the three cannot drift apart.
    """
    return ((last_equity / first_equity) - 1.0) * PERCENT_SCALE


def max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            continue
        dd = (equity / peak) - 1.0
        max_dd = min(max_dd, dd)
    return max_dd * PERCENT_SCALE


def normalize_benchmark_series(benchmark_close: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(benchmark_close, pd.DataFrame):
        if benchmark_close.empty:
            return pd.Series(dtype=float)
        series = benchmark_close.iloc[:, 0]
    else:
        series = benchmark_close

    if isinstance(series, pd.DataFrame):
        if series.empty:
            return pd.Series(dtype=float)
        series = series.iloc[:, 0]

    return pd.to_numeric(series, errors="coerce").dropna()


def benchmark_return_pct(benchmark_close: pd.Series | pd.DataFrame, initial_cash: float) -> float | None:
    series = normalize_benchmark_series(benchmark_close)
    if len(series) < 2:
        return None

    start_px = float(series.iloc[0])
    end_px = float(series.iloc[-1])
    if start_px <= 0:
        return None

    equity = initial_cash * (end_px / start_px)
    return total_return_pct(first_equity=initial_cash, last_equity=equity)


def _equity_return_series(equity_curve: Sequence[float]) -> pd.Series:
    if len(equity_curve) < MIN_RETURN_OBSERVATIONS:
        return pd.Series(dtype=float)
    equity_series = pd.Series(list(equity_curve), dtype=float)
    returns = equity_series.pct_change()
    return returns.replace([float("inf"), float("-inf")], pd.NA).dropna()


def _annualized_return_pct(equity_curve: Sequence[float]) -> float | None:
    if len(equity_curve) < MIN_RETURN_OBSERVATIONS:
        return None
    starting_equity = float(equity_curve[0])
    ending_equity = float(equity_curve[-1])
    observation_count = len(equity_curve) - 1
    if starting_equity <= 0 or ending_equity <= 0 or observation_count <= 0:
        return None
    annualized_return = (ending_equity / starting_equity) ** (
        float(TRADING_DAYS_PER_YEAR) / float(observation_count)
    ) - 1.0
    return annualized_return * PERCENT_SCALE


def sharpe_ratio(returns: pd.Series, *, risk_free_rate: float = 0.0) -> float | None:
    if returns.empty:
        return None
    daily_risk_free_rate = risk_free_rate / float(TRADING_DAYS_PER_YEAR)
    excess_returns = returns - daily_risk_free_rate
    volatility = float(excess_returns.std(ddof=0))
    if volatility <= 0:
        return None
    return float(excess_returns.mean() / volatility * ANNUALIZATION_FACTOR)


def sortino_ratio(returns: pd.Series, *, risk_free_rate: float = 0.0) -> float | None:
    if returns.empty:
        return None
    daily_risk_free_rate = risk_free_rate / float(TRADING_DAYS_PER_YEAR)
    excess_returns = returns - daily_risk_free_rate
    downside_returns = excess_returns[excess_returns < 0]
    if downside_returns.empty:
        return None
    downside_deviation = float((downside_returns.pow(2).mean()) ** 0.5)
    if downside_deviation <= 0:
        return None
    return float(excess_returns.mean() / downside_deviation * ANNUALIZATION_FACTOR)


def calmar_ratio(
    *,
    annualized_return_pct: float | None,
    max_drawdown_pct_value: float,
    drawdown_floor_pct: float = 0.0,
) -> float | None:
    """Annualized return per unit of max-drawdown magnitude, both in percent.

    ``drawdown_floor_pct`` raises the denominator so a (near-)zero-drawdown result
    stays finite and comparable. At the default floor of zero such a result has no
    ratio at all and returns ``None``.
    """
    if annualized_return_pct is None:
        return None
    denominator = max(abs(max_drawdown_pct_value), drawdown_floor_pct)
    return None if denominator <= 0 else annualized_return_pct / denominator


def _coerce_trade_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError(f"Unsupported trade numeric value: {value!r}")


def _normalize_trade_fields(trade: Mapping[str, object]) -> tuple[str, str, float, float, float]:
    return (
        str(trade["ticker"]).upper(),
        str(trade["side"]).lower(),
        _coerce_trade_float(trade["qty"]),
        _coerce_trade_float(trade["price"]),
        _coerce_trade_float(trade["fee"]),
    )


def _closed_trade_stats(trades: Sequence[Mapping[str, object]]) -> tuple[list[float], list[float]]:
    positions: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    cash = 0.0
    realized_pnl = 0.0
    pnl_values: list[float] = []
    return_values: list[float] = []
    for trade in trades:
        ticker, side, qty, price, fee = _normalize_trade_fields(trade)
        if qty <= 0:
            raise ValueError("Trade quantity must be > 0 for backtest metrics.")
        if price < 0:
            raise ValueError("Trade price must be >= 0 for backtest metrics.")
        if side == "buy":
            if price <= 0:
                raise ValueError("Buy trade price must be > 0 for backtest metrics.")
            cash = update_on_buy(ticker, qty, price, fee, positions, avg_cost, cash)
            continue
        if side != "sell":
            raise ValueError(f"Unsupported trade side {side!r} for backtest metrics.")
        if qty > positions[ticker]:
            raise ValueError(f"Invalid sell for {ticker}: trying to sell {qty}, holding {positions[ticker]}.")
        cost_basis = avg_cost[ticker] * qty
        pnl = ((price - avg_cost[ticker]) * qty) - fee
        cash, realized_pnl = update_on_sell(
            ticker,
            qty,
            price,
            fee,
            positions,
            avg_cost,
            cash,
            realized_pnl,
        )
        pnl_values.append(pnl)
        if cost_basis > 0:
            return_values.append((pnl / cost_basis) * PERCENT_SCALE)
    return pnl_values, return_values


def summarize_backtest_performance(
    equity_curve: Sequence[float],
    trades: Sequence[Mapping[str, object]],
    *,
    risk_free_rate: float = 0.0,
) -> BacktestPerformanceMetrics:
    returns = _equity_return_series(equity_curve)
    annualized_return = _annualized_return_pct(equity_curve)
    pnl_values, return_values = _closed_trade_stats(trades)
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = sum(-value for value in pnl_values if value < 0)
    win_count = sum(1 for value in pnl_values if value > 0)
    closed_trade_count = len(pnl_values)
    return BacktestPerformanceMetrics(
        annualized_return_pct=annualized_return,
        sharpe_ratio=sharpe_ratio(returns, risk_free_rate=risk_free_rate),
        sortino_ratio=sortino_ratio(returns, risk_free_rate=risk_free_rate),
        calmar_ratio=calmar_ratio(
            annualized_return_pct=annualized_return,
            max_drawdown_pct_value=max_drawdown_pct(list(equity_curve)),
        ),
        win_rate_pct=(
            (float(win_count) / float(closed_trade_count)) * PERCENT_SCALE if closed_trade_count > 0 else None
        ),
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        avg_trade_return_pct=(sum(return_values) / float(len(return_values)) if return_values else None),
    )
