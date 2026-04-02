from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any, Callable, cast

from common.constants import BASIS_POINTS_DIVISOR

# Fraction of total portfolio equity allocated per buy signal
POSITION_SIZE_PCT = 0.10


def run_backtest(
    conn: sqlite3.Connection,
    cfg,
    *,
    get_account_fn: Callable[[sqlite3.Connection, str], sqlite3.Row],
    resolve_backtest_dates_fn: Callable[..., tuple[date, date]],
    warnings_for_config_fn: Callable[[sqlite3.Row, bool], list[str]],
    resolve_universe_fn: Callable[..., tuple[list[str], dict[str, list[str]], list[str], list[str]]],
    fetch_close_history_fn: Callable[..., object],
    fetch_benchmark_close_fn: Callable[..., object],
    row_expect_str_fn: Callable[[sqlite3.Row, str], str],
    row_expect_int_fn: Callable[[sqlite3.Row, str], int],
    row_expect_float_fn: Callable[[sqlite3.Row, str], float],
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str],
    resolve_strategy_fn,
    get_feature_provider_fn,
    insert_run_fn: Callable[..., int],
    compute_market_value_fn: Callable[[dict[str, float], dict[str, float]], float],
    compute_unrealized_pnl_fn: Callable[[dict[str, float], dict[str, float], dict[str, float]], float],
    update_on_buy_fn,
    update_on_sell_fn,
    insert_trade_fn,
    insert_snapshot_fn,
    resolve_signal_fn,
    benchmark_return_pct_fn: Callable[[object, float], float | None],
    max_drawdown_pct_fn: Callable[[list[float]], float],
    backtest_result_cls,
):
    account = get_account_fn(conn, cfg.account_name)
    start_date, end_date = resolve_backtest_dates_fn(cfg.start, cfg.end, cfg.lookback_months)
    warnings = warnings_for_config_fn(account, cfg.allow_approximate_leaps)

    default_tickers, month_to_tickers, all_tickers, universe_warnings = resolve_universe_fn(
        cfg,
        start_date,
        end_date,
    )
    warnings.extend(universe_warnings)

    close = cast(Any, fetch_close_history_fn(all_tickers, start_date, end_date))
    if len(close.index) < 3:
        raise ValueError("Not enough historical bars in selected range. Need at least 3 trading days.")

    benchmark_ticker = row_expect_str_fn(account, "benchmark_ticker")
    account_id = row_expect_int_fn(account, "id")
    initial_cash = row_expect_float_fn(account, "initial_cash")
    strategy_name = resolve_active_strategy_fn(account)
    strategy_spec = resolve_strategy_fn(strategy_name)

    benchmark_series = fetch_benchmark_close_fn(benchmark_ticker, start_date, end_date)

    feature_bundle = None
    if strategy_spec.required_features:
        feature_bundle = get_feature_provider_fn().build_feature_bundle(all_tickers, start_date, end_date, close)
        warnings.extend(feature_bundle.warnings)

    run_id = insert_run_fn(conn, account_id, strategy_name, start_date, end_date, cfg, warnings)

    cash = initial_cash
    realized_pnl = 0.0
    positions: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    slippage_multiplier_buy = 1.0 + (cfg.slippage_bps / BASIS_POINTS_DIVISOR)
    slippage_multiplier_sell = 1.0 - (cfg.slippage_bps / BASIS_POINTS_DIVISOR)

    equity_curve: list[float] = []
    trade_count = 0

    dates = list(close.index)
    first_prices = {ticker: float(close.loc[dates[0], ticker]) for ticker in all_tickers}
    first_mv = compute_market_value_fn(positions, first_prices)
    first_equity = cash + first_mv
    insert_snapshot_fn(
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
        held_tickers = [ticker for ticker, qty in positions.items() if qty > 0]
        strategy_tickers = sorted(set(active_tickers) | set(held_tickers))

        for ticker in strategy_tickers:
            history = close.loc[:signal_date, ticker].dropna()
            feature_history = None if feature_bundle is None else feature_bundle.history_for_ticker(ticker, signal_date)
            if feature_history is None:
                signal = resolve_signal_fn(strategy_name, history)
            else:
                signal = resolve_signal_fn(strategy_name, history, feature_history=feature_history)

            if signal == "buy" and ticker not in active_tickers:
                continue

            if signal == "buy" and positions[ticker] <= 0:
                px = float(trade_prices[ticker])
                if px <= 0:
                    continue

                allocation = (cash + compute_market_value_fn(positions, trade_prices.to_dict())) * POSITION_SIZE_PCT
                exec_px = px * slippage_multiplier_buy
                if exec_px <= 0:
                    continue

                qty_int = math.floor(max(0.0, allocation - cfg.fee_per_trade) / exec_px)
                if qty_int < 1:
                    continue

                required = (qty_int * exec_px) + cfg.fee_per_trade
                if required > cash:
                    continue

                cash = update_on_buy_fn(ticker, float(qty_int), exec_px, cfg.fee_per_trade, positions, avg_cost, cash)
                trade_count += 1
                insert_trade_fn(
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

                cash, realized_pnl = update_on_sell_fn(
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
                insert_trade_fn(
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
        market_value = compute_market_value_fn(positions, marks)
        unrealized_pnl = compute_unrealized_pnl_fn(positions, avg_cost, marks)

        equity = cash + market_value
        equity_curve.append(equity)
        insert_snapshot_fn(
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
    benchmark_return = benchmark_return_pct_fn(benchmark_series, initial_cash)
    alpha_pct = None if benchmark_return is None else total_return_pct - benchmark_return

    return backtest_result_cls(
        run_id=run_id,
        account_name=cfg.account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        tickers=all_tickers,
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return,
        alpha_pct=alpha_pct,
        max_drawdown_pct=max_drawdown_pct_fn(equity_curve),
        warnings=warnings,
    )
