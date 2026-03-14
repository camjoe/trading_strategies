from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import pandas as pd

try:
    from trading.accounts import get_account, utc_now_iso
    from trading.backtest_data import fetch_benchmark_close, fetch_close_history, load_tickers_from_file, resolve_backtest_dates
except ModuleNotFoundError:
    from accounts import get_account, utc_now_iso
    from backtest_data import fetch_benchmark_close, fetch_close_history, load_tickers_from_file, resolve_backtest_dates


@dataclass
class BacktestConfig:
    account_name: str
    tickers_file: str
    start: str | None
    end: str | None
    lookback_months: int | None
    slippage_bps: float
    fee_per_trade: float
    run_name: str | None
    allow_approximate_leaps: bool


@dataclass
class BacktestResult:
    run_id: int
    account_name: str
    start_date: str
    end_date: str
    tickers: list[str]
    trade_count: int
    ending_equity: float
    total_return_pct: float
    benchmark_return_pct: float | None
    alpha_pct: float | None
    max_drawdown_pct: float
    warnings: list[str]


def _strategy_signal(strategy_name: str, history: pd.Series) -> str:
    if len(history) < 30:
        return "hold"

    close = float(history.iloc[-1])
    sma_10 = float(history.tail(10).mean())
    sma_20 = float(history.tail(20).mean())

    name = strategy_name.lower()
    if "mean" in name or "reversion" in name:
        if close < (sma_20 * 0.98):
            return "buy"
        if close > (sma_20 * 1.02):
            return "sell"
        return "hold"

    # Default trend/momentum proxy.
    if close > sma_10 > sma_20:
        return "buy"
    if close < sma_10:
        return "sell"
    return "hold"


def _max_drawdown_pct(equity_curve: list[float]) -> float:
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
    return max_dd * 100.0


def _compute_market_value(positions: dict[str, float], prices: dict[str, float]) -> float:
    total = 0.0
    for ticker, qty in positions.items():
        px = prices.get(ticker)
        if px is None:
            continue
        total += qty * px
    return total


def _update_on_buy(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
) -> float:
    old_qty = positions[ticker]
    new_qty = old_qty + qty
    old_value = old_qty * avg_cost[ticker]
    trade_value = (qty * price) + fee
    avg_cost[ticker] = (old_value + trade_value) / new_qty
    positions[ticker] = new_qty
    return cash - trade_value


def _update_on_sell(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
    realized_pnl: float,
) -> tuple[float, float]:
    proceeds = (qty * price) - fee
    cash += proceeds
    realized_pnl += ((price - avg_cost[ticker]) * qty) - fee
    positions[ticker] -= qty
    if positions[ticker] <= 0:
        positions[ticker] = 0.0
        avg_cost[ticker] = 0.0
    return cash, realized_pnl


def _warnings_for_config(account: sqlite3.Row, allow_approximate_leaps: bool) -> list[str]:
    warnings: list[str] = [
        "Backtest uses adjusted daily close data only; intraday price path is not modeled.",
        "Universe file may include survivorship bias if it only reflects currently listed symbols.",
    ]

    if account["risk_policy"] in {"fixed_stop", "take_profit", "stop_and_target"}:
        warnings.append(
            "Stop-loss/take-profit checks are approximated on daily closes and can differ from intraday execution."
        )

    if account["instrument_mode"] == "leaps":
        if not allow_approximate_leaps:
            raise ValueError(
                "LEAPs mode backtesting is approximate only. Re-run with --allow-approximate-leaps to continue."
            )
        warnings.append(
            "LEAPs mode is approximated using underlying equity prices; options chain history and Greeks are not modeled."
        )

    return warnings


def _insert_run(
    conn: sqlite3.Connection,
    account_id: int,
    start_date: date,
    end_date: date,
    cfg: BacktestConfig,
    warnings: list[str],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            run_name,
            start_date,
            end_date,
            created_at,
            slippage_bps,
            fee_per_trade,
            tickers_file,
            notes,
            warnings
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            cfg.run_name,
            start_date.isoformat(),
            end_date.isoformat(),
            utc_now_iso(),
            float(cfg.slippage_bps),
            float(cfg.fee_per_trade),
            cfg.tickers_file,
            "First working backtest version: deterministic daily-bar simulator.",
            " | ".join(warnings),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _insert_trade(
    conn: sqlite3.Connection,
    run_id: int,
    trade_time: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    slippage_bps: float,
    note: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_trades (
            run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note),
    )


def _insert_snapshot(
    conn: sqlite3.Connection,
    run_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
    )


def _benchmark_return_pct(benchmark_close: pd.Series, initial_cash: float) -> float | None:
    series = benchmark_close.dropna()
    if len(series) < 2:
        return None

    start_px = float(series.iloc[0])
    end_px = float(series.iloc[-1])
    if start_px <= 0:
        return None

    equity = initial_cash * (end_px / start_px)
    return ((equity / initial_cash) - 1.0) * 100.0


def run_backtest(conn: sqlite3.Connection, cfg: BacktestConfig) -> BacktestResult:
    account = get_account(conn, cfg.account_name)
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    warnings = _warnings_for_config(account, cfg.allow_approximate_leaps)

    tickers = load_tickers_from_file(cfg.tickers_file)
    close = fetch_close_history(tickers, start_date, end_date)
    if len(close.index) < 3:
        raise ValueError("Not enough historical bars in selected range. Need at least 3 trading days.")

    benchmark_series = fetch_benchmark_close(account["benchmark_ticker"], start_date, end_date)

    run_id = _insert_run(conn, account["id"], start_date, end_date, cfg, warnings)

    cash = float(account["initial_cash"])
    realized_pnl = 0.0
    positions: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    slippage_multiplier_buy = 1.0 + (cfg.slippage_bps / 10_000.0)
    slippage_multiplier_sell = 1.0 - (cfg.slippage_bps / 10_000.0)

    equity_curve: list[float] = []
    trade_count = 0

    dates = list(close.index)
    first_prices = {ticker: float(close.loc[dates[0], ticker]) for ticker in tickers}
    first_mv = _compute_market_value(positions, first_prices)
    first_equity = cash + first_mv
    _insert_snapshot(
        conn,
        run_id,
        dates[0].date().isoformat(),
        cash,
        first_mv,
        first_equity,
        realized_pnl,
        0.0,
    )
    equity_curve.append(first_equity)

    for idx in range(1, len(dates)):
        signal_date = dates[idx - 1]
        trade_date = dates[idx]

        signal_prices = close.loc[signal_date]
        trade_prices = close.loc[trade_date]

        for ticker in tickers:
            history = close.loc[:signal_date, ticker].dropna()
            signal = _strategy_signal(str(account["strategy"]), history)

            if signal == "buy" and positions[ticker] <= 0:
                px = float(trade_prices[ticker])
                if px <= 0:
                    continue

                allocation = (cash + _compute_market_value(positions, trade_prices.to_dict())) * 0.10
                exec_px = px * slippage_multiplier_buy
                if exec_px <= 0:
                    continue

                qty = math.floor(max(0.0, allocation - cfg.fee_per_trade) / exec_px)
                if qty < 1:
                    continue

                required = (qty * exec_px) + cfg.fee_per_trade
                if required > cash:
                    continue

                cash = _update_on_buy(ticker, float(qty), exec_px, cfg.fee_per_trade, positions, avg_cost, cash)
                trade_count += 1
                _insert_trade(
                    conn,
                    run_id,
                    trade_date.date().isoformat(),
                    ticker,
                    "buy",
                    float(qty),
                    exec_px,
                    cfg.fee_per_trade,
                    cfg.slippage_bps,
                    "signal=buy",
                )

            if signal == "sell" and positions[ticker] > 0:
                px = float(trade_prices[ticker])
                if px <= 0:
                    continue

                exec_px = px * slippage_multiplier_sell
                qty = float(positions[ticker])
                if qty <= 0:
                    continue

                cash, realized_pnl = _update_on_sell(
                    ticker,
                    qty,
                    exec_px,
                    cfg.fee_per_trade,
                    positions,
                    avg_cost,
                    cash,
                    realized_pnl,
                )
                trade_count += 1
                _insert_trade(
                    conn,
                    run_id,
                    trade_date.date().isoformat(),
                    ticker,
                    "sell",
                    qty,
                    exec_px,
                    cfg.fee_per_trade,
                    cfg.slippage_bps,
                    "signal=sell",
                )

        marks = {ticker: float(trade_prices[ticker]) for ticker in tickers}
        market_value = _compute_market_value(positions, marks)
        unrealized_pnl = 0.0
        for ticker, qty in positions.items():
            if qty <= 0:
                continue
            unrealized_pnl += (marks[ticker] - avg_cost[ticker]) * qty

        equity = cash + market_value
        equity_curve.append(equity)
        _insert_snapshot(
            conn,
            run_id,
            trade_date.date().isoformat(),
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl,
        )

    conn.commit()

    ending_equity = equity_curve[-1]
    total_return_pct = ((ending_equity / float(account["initial_cash"])) - 1.0) * 100.0
    benchmark_return_pct = _benchmark_return_pct(benchmark_series, float(account["initial_cash"]))
    alpha_pct = None if benchmark_return_pct is None else total_return_pct - benchmark_return_pct

    return BacktestResult(
        run_id=run_id,
        account_name=cfg.account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        tickers=tickers,
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        warnings=warnings,
    )


def backtest_report(conn: sqlite3.Connection, run_id: int) -> dict[str, object]:
    run = conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
               r.tickers_file, r.notes, r.warnings, a.name AS account_name, a.strategy, a.benchmark_ticker
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()
    if run is None:
        raise ValueError(f"Backtest run id {run_id} not found")

    snapshots = conn.execute(
        """
        SELECT snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM backtest_equity_snapshots
        WHERE run_id = ?
        ORDER BY snapshot_time, id
        """,
        (run_id,),
    ).fetchall()
    trades = conn.execute(
        """
        SELECT trade_time, ticker, side, qty, price, fee
        FROM backtest_trades
        WHERE run_id = ?
        ORDER BY trade_time, id
        """,
        (run_id,),
    ).fetchall()

    if not snapshots:
        raise ValueError(f"Backtest run id {run_id} has no equity snapshots")

    first_equity = float(snapshots[0]["equity"])
    last_equity = float(snapshots[-1]["equity"])
    total_return_pct = ((last_equity / first_equity) - 1.0) * 100.0 if first_equity > 0 else 0.0
    max_drawdown = _max_drawdown_pct([float(r["equity"]) for r in snapshots])

    return {
        "run_id": int(run["id"]),
        "run_name": run["run_name"],
        "account_name": run["account_name"],
        "strategy": run["strategy"],
        "benchmark_ticker": run["benchmark_ticker"],
        "start_date": run["start_date"],
        "end_date": run["end_date"],
        "created_at": run["created_at"],
        "slippage_bps": float(run["slippage_bps"]),
        "fee_per_trade": float(run["fee_per_trade"]),
        "tickers_file": run["tickers_file"],
        "notes": run["notes"],
        "warnings": str(run["warnings"] or ""),
        "trade_count": len(trades),
        "starting_equity": first_equity,
        "ending_equity": last_equity,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_drawdown,
    }
