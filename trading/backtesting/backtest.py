from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date

import pandas as pd

from common.market_data import get_feature_provider
from trading.accounts import get_account
from trading.backtesting.domain.metrics import benchmark_return_pct, max_drawdown_pct, normalize_benchmark_series
from trading.backtesting.domain.risk_warnings import build_backtest_warnings
from trading.backtesting.domain.simulation_math import (
    compute_market_value,
    compute_unrealized_pnl,
    update_on_buy,
    update_on_sell,
)
from trading.backtesting.domain.strategy_signals import resolve_signal, resolve_strategy
from trading.backtesting.domain.windowing import add_months
from trading.backtesting.domain.windowing import build_walk_forward_windows as build_walk_forward_windows_impl
from trading.backtesting.repositories.backtest_repository import (
    insert_backtest_run,
    insert_backtest_snapshot,
    insert_backtest_trade,
)
from trading.backtesting.services.backtest_data_service import (
    build_monthly_universe,
    fetch_benchmark_close,
    fetch_close_history,
    load_tickers_from_file,
    resolve_backtest_dates,
)
from trading.backtesting.services.leaderboard_service import load_backtest_leaderboard_entries
from trading.backtesting.services.report_service import load_backtest_report_data
from trading.backtesting.services.walk_forward_service import execute_walk_forward_backtest
from trading.coercion import (
    row_expect_float,
    row_expect_int,
    row_expect_str,
)
from trading.models.backtesting import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
    WalkForwardConfig,
    WalkForwardSummary,
)
from trading.models.backtesting_reports import BacktestFullReport, BacktestLeaderboardEntry, BacktestReportSummary
from trading.rotation import resolve_active_strategy


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    return max_drawdown_pct(equity_curve)


def _add_months(base: date, months: int) -> date:
    return add_months(base, months)


def build_walk_forward_windows(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> list[tuple[date, date]]:
    return build_walk_forward_windows_impl(start_date, end_date, test_months, step_months)


def _compute_market_value(positions: dict[str, float], prices: dict[str, float]) -> float:
    return compute_market_value(positions, prices)


def _update_on_buy(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
) -> float:
    return update_on_buy(ticker, qty, price, fee, positions, avg_cost, cash)


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
    return update_on_sell(ticker, qty, price, fee, positions, avg_cost, cash, realized_pnl)


def _warnings_for_config(account: sqlite3.Row, allow_approximate_leaps: bool) -> list[str]:
    return build_backtest_warnings(account, allow_approximate_leaps=allow_approximate_leaps)


def _resolve_universe(
    cfg: BacktestConfig,
    start_date: date,
    end_date: date,
) -> tuple[list[str], dict[str, list[str]], list[str], list[str]]:
    default_tickers = load_tickers_from_file(cfg.tickers_file)
    month_to_tickers, all_tickers, warnings = build_monthly_universe(
        default_tickers,
        start_date,
        end_date,
        cfg.universe_history_dir,
    )

    if cfg.universe_history_dir:
        warnings.append(
            "Monthly universe reconstitution enabled from snapshot files; ticker membership can change each month."
        )

    return default_tickers, month_to_tickers, all_tickers, warnings


def _compute_unrealized_pnl(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    marks: dict[str, float],
) -> float:
    return compute_unrealized_pnl(positions, avg_cost, marks)


def _normalize_benchmark_series(benchmark_close: pd.Series | pd.DataFrame) -> pd.Series:
    return normalize_benchmark_series(benchmark_close)


def _benchmark_return_pct(benchmark_close: pd.Series | pd.DataFrame, initial_cash: float) -> float | None:
    return benchmark_return_pct(benchmark_close, initial_cash)


def preview_backtest_warnings(conn: sqlite3.Connection, cfg: BacktestConfig) -> list[str]:
    account = get_account(conn, cfg.account_name)
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    warnings = _warnings_for_config(account, cfg.allow_approximate_leaps)

    _default_tickers, _month_to_tickers, _all_tickers, universe_warnings = _resolve_universe(
        cfg,
        start_date,
        end_date,
    )
    warnings.extend(universe_warnings)

    return warnings


def _insert_run(
    conn: sqlite3.Connection,
    account_id: int,
    strategy_name: str,
    start_date: date,
    end_date: date,
    cfg: BacktestConfig,
    warnings: list[str],
) -> int:
    return insert_backtest_run(
        conn,
        account_id=account_id,
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
        cfg=cfg,
        warnings=warnings,
    )


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
    insert_backtest_trade(
        conn,
        run_id=run_id,
        trade_time=trade_time,
        ticker=ticker,
        side=side,
        qty=qty,
        price=price,
        fee=fee,
        slippage_bps=slippage_bps,
        note=note,
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
    insert_backtest_snapshot(
        conn,
        run_id=run_id,
        snapshot_time=snapshot_time,
        cash=cash,
        market_value=market_value,
        equity=equity,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
    )


def run_backtest(conn: sqlite3.Connection, cfg: BacktestConfig) -> BacktestResult:
    account = get_account(conn, cfg.account_name)
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    warnings = _warnings_for_config(account, cfg.allow_approximate_leaps)

    default_tickers, month_to_tickers, all_tickers, universe_warnings = _resolve_universe(
        cfg,
        start_date,
        end_date,
    )
    warnings.extend(universe_warnings)

    close = fetch_close_history(all_tickers, start_date, end_date)
    if len(close.index) < 3:
        raise ValueError("Not enough historical bars in selected range. Need at least 3 trading days.")

    benchmark_ticker = row_expect_str(account, "benchmark_ticker")
    account_id = row_expect_int(account, "id")
    initial_cash = row_expect_float(account, "initial_cash")
    strategy_name = resolve_active_strategy(account)
    strategy_spec = resolve_strategy(strategy_name)

    benchmark_series = fetch_benchmark_close(benchmark_ticker, start_date, end_date)

    feature_bundle = None
    if strategy_spec.required_features:
        feature_bundle = get_feature_provider().build_feature_bundle(all_tickers, start_date, end_date, close)
        warnings.extend(feature_bundle.warnings)

    run_id = _insert_run(conn, account_id, strategy_name, start_date, end_date, cfg, warnings)

    cash = initial_cash
    realized_pnl = 0.0
    positions: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    slippage_multiplier_buy = 1.0 + (cfg.slippage_bps / 10_000.0)
    slippage_multiplier_sell = 1.0 - (cfg.slippage_bps / 10_000.0)

    equity_curve: list[float] = []
    trade_count = 0

    dates = list(close.index)
    first_prices = {ticker: float(close.loc[dates[0], ticker]) for ticker in all_tickers}
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

        trade_prices = close.loc[trade_date]
        month_key = f"{signal_date.year:04d}-{signal_date.month:02d}"
        active_tickers = month_to_tickers.get(month_key, default_tickers)
        held_tickers = [t for t, q in positions.items() if q > 0]
        strategy_tickers = sorted(set(active_tickers) | set(held_tickers))

        for ticker in strategy_tickers:
            history = close.loc[:signal_date, ticker].dropna()
            feature_history = None if feature_bundle is None else feature_bundle.history_for_ticker(ticker, signal_date)
            if feature_history is None:
                signal = resolve_signal(strategy_name, history)
            else:
                signal = resolve_signal(strategy_name, history, feature_history=feature_history)

            if signal == "buy" and ticker not in active_tickers:
                continue

            if signal == "buy" and positions[ticker] <= 0:
                px = float(trade_prices[ticker])
                if px <= 0:
                    continue

                allocation = (cash + _compute_market_value(positions, trade_prices.to_dict())) * 0.10
                exec_px = px * slippage_multiplier_buy
                if exec_px <= 0:
                    continue

                qty_int = math.floor(max(0.0, allocation - cfg.fee_per_trade) / exec_px)
                if qty_int < 1:
                    continue

                required = (qty_int * exec_px) + cfg.fee_per_trade
                if required > cash:
                    continue

                cash = _update_on_buy(ticker, float(qty_int), exec_px, cfg.fee_per_trade, positions, avg_cost, cash)
                trade_count += 1
                _insert_trade(
                    conn,
                    run_id,
                    trade_date.date().isoformat(),
                    ticker,
                    "buy",
                    float(qty_int),
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
                qty_float = float(positions[ticker])
                if qty_float <= 0:
                    continue

                cash, realized_pnl = _update_on_sell(
                    ticker,
                    qty_float,
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
                    qty_float,
                    exec_px,
                    cfg.fee_per_trade,
                    cfg.slippage_bps,
                    "signal=sell",
                )

        marks = {ticker: float(trade_prices[ticker]) for ticker in all_tickers}
        market_value = _compute_market_value(positions, marks)
        unrealized_pnl = _compute_unrealized_pnl(positions, avg_cost, marks)

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
    total_return_pct = ((ending_equity / initial_cash) - 1.0) * 100.0
    benchmark_return_pct = _benchmark_return_pct(benchmark_series, initial_cash)
    alpha_pct = None if benchmark_return_pct is None else total_return_pct - benchmark_return_pct

    return BacktestResult(
        run_id=run_id,
        account_name=cfg.account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        tickers=all_tickers,
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        warnings=warnings,
    )


def backtest_report(conn: sqlite3.Connection, run_id: int) -> dict[str, object]:
    return backtest_report_full(conn, run_id).to_payload()


def backtest_report_full(conn: sqlite3.Connection, run_id: int) -> BacktestFullReport:
    return _load_backtest_report_data(conn, run_id)


def _load_backtest_report_data(conn: sqlite3.Connection, run_id: int) -> BacktestFullReport:
    return load_backtest_report_data(conn, run_id=run_id, fetch_benchmark_close_fn=fetch_benchmark_close)


def backtest_report_summary(conn: sqlite3.Connection, run_id: int) -> BacktestReportSummary:
    return _load_backtest_report_data(conn, run_id).summary


def backtest_leaderboard(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
    account_name: str | None = None,
    strategy: str | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entry, starting_equity in _load_backtest_leaderboard_entries(
        conn,
        limit=limit,
        account_name=account_name,
        strategy=strategy,
    ):
        row = {
            "run_id": entry.run_id,
            "run_name": entry.run_name,
            "account_name": entry.account_name,
            "strategy": entry.strategy,
            "start_date": entry.start_date,
            "end_date": entry.end_date,
            "created_at": entry.created_at,
            "trade_count": entry.trade_count,
            "ending_equity": entry.ending_equity,
            "total_return_pct": entry.total_return_pct,
            "max_drawdown_pct": entry.max_drawdown_pct,
            "benchmark_return_pct": entry.benchmark_return_pct,
            "alpha_pct": entry.alpha_pct,
        }
        row["starting_equity"] = starting_equity
        rows.append(row)
    return rows


def backtest_leaderboard_entries(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
    account_name: str | None = None,
    strategy: str | None = None,
) -> list[BacktestLeaderboardEntry]:
    return [
        entry
        for entry, _starting_equity in _load_backtest_leaderboard_entries(
            conn,
            limit=limit,
            account_name=account_name,
            strategy=strategy,
        )
    ]


def _load_backtest_leaderboard_entries(
    conn: sqlite3.Connection,
    *,
    limit: int,
    account_name: str | None,
    strategy: str | None,
) -> list[tuple[BacktestLeaderboardEntry, float]]:
    return load_backtest_leaderboard_entries(
        conn,
        limit=limit,
        account_name=account_name,
        strategy=strategy,
        fetch_benchmark_close_fn=fetch_benchmark_close,
    )


def run_backtest_batch(conn: sqlite3.Connection, cfg: BacktestBatchConfig) -> list[BacktestResult]:
    account_names = [name.strip() for name in cfg.account_names if name.strip()]
    if not account_names:
        raise ValueError("At least one account name is required.")

    results: list[BacktestResult] = []
    for idx, account_name in enumerate(account_names, start=1):
        run_name = None
        if cfg.run_name_prefix:
            run_name = f"{cfg.run_name_prefix}_{idx:02d}_{account_name}"

        result = run_backtest(
            conn,
            BacktestConfig(
                account_name=account_name,
                tickers_file=cfg.tickers_file,
                universe_history_dir=cfg.universe_history_dir,
                start=cfg.start,
                end=cfg.end,
                lookback_months=cfg.lookback_months,
                slippage_bps=cfg.slippage_bps,
                fee_per_trade=cfg.fee_per_trade,
                run_name=run_name,
                allow_approximate_leaps=cfg.allow_approximate_leaps,
            ),
        )
        results.append(result)

    results.sort(key=lambda item: item.total_return_pct, reverse=True)
    return results


def run_walk_forward_backtest(
    conn: sqlite3.Connection,
    cfg: WalkForwardConfig,
) -> WalkForwardSummary:
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    windows = build_walk_forward_windows(start_date, end_date, cfg.test_months, cfg.step_months)

    return execute_walk_forward_backtest(
        conn,
        cfg=cfg,
        start_date=start_date,
        end_date=end_date,
        windows=windows,
        run_backtest_fn=run_backtest,
    )
