from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, cast

from common.coercion import row_expect_float, row_expect_int, row_expect_str
from common.constants import BASIS_POINTS_DIVISOR
from trading.backtesting.domain.bars import build_bar_panel
from trading.backtesting.domain.metrics import benchmark_return_pct, max_drawdown_pct, summarize_backtest_performance
from trading.backtesting.domain.simulation_math import (
    compute_market_value,
    compute_unrealized_pnl,
    update_on_buy,
    update_on_sell,
)
from trading.backtesting.domain.windowing import shift_months
from trading.backtesting.models import BacktestResult
from trading.domain.auto_trading_policy import (
    allocate_buy_quantities as default_allocate_buy_quantities,
    choose_buy_qty as default_choose_buy_qty,
)
from trading.domain.strategies.indicator_view import (
    IndicatorView,
    build_indicator_arrays,
    count_priced_bars,
)
from trading.domain.strategies.resolution import evaluate_signal, resolve_strategy
from trading.models.market_data.constants import BAR_CLOSE
from trading.repositories.unit_of_work import unit_of_work
from trading.services.books.book_assignments import active_strategy_for_account, get_default_book
from trading.services.market_data import FeatureDataProvider, require_feature_provider

AccountRow = Mapping[str, object]


def _tradeable_price(raw: Any) -> float | None:
    """The bar's price if it can be traded on, else None.

    A ticker has no price before its first bar — the panel leaves those days
    empty rather than inventing one that predates the listing. NaN loses every
    ordinary comparison, so a bare ``price <= 0`` check waves it through; it
    then reaches ``choose_buy_qty`` and aborts the whole run with "cannot
    convert float NaN to integer". Screening here keeps a universe that contains
    a late listing runnable, skipping the ticker until it has a price.
    """
    price = float(raw)
    if not math.isfinite(price) or price <= 0:
        return None
    return price


@dataclass
class _PortfolioState:
    """What the simulation carries from one bar to the next.

    Mutable by design: the bar phases advance it in place, the way the single
    loop did before they were separated out.
    """

    cash: float
    realized_pnl: float = 0.0
    positions: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    avg_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    trade_count: int = 0
    executed_trades: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class _ExecutionContext:
    """Everything a bar's phases need that does not change between bars."""

    conn: sqlite3.Connection
    run_id: int
    cfg: Any
    slippage_multiplier_buy: float
    slippage_multiplier_sell: float
    insert_trade_fn: Any
    choose_buy_qty_fn: Callable[..., int]
    allocate_buy_quantities_fn: Callable[..., dict[str, int]]
    default_book: Any


def _record_trade(
    ctx: _ExecutionContext,
    state: _PortfolioState,
    *,
    trade_date: Any,
    ticker: str,
    side: str,
    qty: float,
    exec_px: float,
    note: str,
) -> None:
    state.trade_count += 1
    ctx.insert_trade_fn(
        ctx.conn,
        ctx.run_id,
        trade_date.date().isoformat(),
        ticker,
        side,
        qty,
        exec_px,
        ctx.cfg.fee_per_trade,
        ctx.cfg.slippage_bps,
        note,
    )
    state.executed_trades.append(
        {"ticker": ticker, "side": side, "qty": qty, "price": exec_px, "fee": ctx.cfg.fee_per_trade}
    )


def _execute_sells(
    ctx: _ExecutionContext,
    state: _PortfolioState,
    *,
    trade_date: Any,
    trade_prices: Any,
    signals: dict[str, str],
    tickers: list[str],
) -> None:
    """Close signalled positions. Runs before buys so the proceeds are spendable."""
    for ticker in tickers:
        if signals[ticker] != "sell" or state.positions[ticker] <= 0:
            continue
        px = _tradeable_price(trade_prices[ticker])
        if px is None:
            continue

        exec_px = px * ctx.slippage_multiplier_sell
        qty_float = float(state.positions[ticker])
        if qty_float <= 0:
            continue

        state.cash, state.realized_pnl = update_on_sell(
            ticker,
            qty_float,
            exec_px,
            ctx.cfg.fee_per_trade,
            state.positions,
            state.avg_cost,
            state.cash,
            state.realized_pnl,
        )
        _record_trade(
            ctx,
            state,
            trade_date=trade_date,
            ticker=ticker,
            side="sell",
            qty=qty_float,
            exec_px=exec_px,
            note="signal=sell",
        )


def _execute_buys(
    ctx: _ExecutionContext,
    state: _PortfolioState,
    *,
    trade_date: Any,
    trade_prices: Any,
    signals: dict[str, str],
    tickers: list[str],
    active_tickers: list[str],
) -> None:
    """Open signalled positions, sharing the bar's cash across all of them."""
    # Every buy is sized against the same post-sell equity, so sizing does not
    # drift as earlier buys in the list execute.
    post_sell_equity = state.cash + compute_market_value(state.positions, trade_prices.to_dict())
    sized_buys: list[tuple[str, float, int]] = []
    for ticker in tickers:
        if signals[ticker] != "buy" or ticker not in active_tickers or state.positions[ticker] > 0:
            continue
        px = _tradeable_price(trade_prices[ticker])
        if px is None:
            continue
        exec_px = px * ctx.slippage_multiplier_buy
        if exec_px <= 0:
            continue
        requested_qty = ctx.choose_buy_qty_fn(
            state.cash,
            exec_px,
            ctx.cfg.fee_per_trade,
            trade_size_pct=ctx.default_book.trade_size_pct if ctx.default_book is not None else None,
            max_position_pct=ctx.default_book.max_position_pct if ctx.default_book is not None else None,
            current_position_value=float(state.positions[ticker]) * px,
            portfolio_equity=post_sell_equity,
        )
        if requested_qty >= 1:
            sized_buys.append((ticker, exec_px, requested_qty))

    granted = ctx.allocate_buy_quantities_fn(sized_buys, cash=state.cash, fee_per_trade=ctx.cfg.fee_per_trade)
    for ticker, exec_px, requested_qty in sized_buys:
        qty_int = granted.get(ticker, 0)
        if qty_int < 1:
            continue

        state.cash = update_on_buy(
            ticker, float(qty_int), exec_px, ctx.cfg.fee_per_trade, state.positions, state.avg_cost, state.cash
        )
        _record_trade(
            ctx,
            state,
            trade_date=trade_date,
            ticker=ticker,
            side="buy",
            qty=float(qty_int),
            exec_px=exec_px,
            # Record when the bar's cash could not fund the full signal set —
            # otherwise a scaled position looks like the strategy asked for less.
            note="signal=buy" if qty_int == requested_qty else "signal=buy (cash-scaled)",
        )


def _first_scoring_index(dates: list, scoring_start: date) -> int:
    """Index of the first loaded bar that falls on/after the scoring window start.
    Earlier bars are warm-up history. With no warm-up this is 0 (bar zero)."""
    for index, timestamp in enumerate(dates):
        if timestamp.date() >= scoring_start:
            return index
    raise ValueError("No trading days fall within the scoring window.")


def run_backtest(
    conn: sqlite3.Connection,
    cfg,
    *,
    get_account_fn: Callable[[sqlite3.Connection, str], AccountRow],
    resolve_backtest_dates_fn: Callable[..., tuple[date, date]],
    warnings_for_config_fn: Callable[[Any, bool], list[str]],
    resolve_universe_fn: Callable[..., tuple[list[str], dict[str, list[str]], list[str], list[str]]],
    fetch_bar_history_fn: Callable[..., Mapping[str, Any]],
    fetch_benchmark_close_fn: Callable[..., object],
    insert_run_fn: Callable[..., int],
    insert_trade_fn,
    insert_snapshot_fn,
    choose_buy_qty_fn: Callable[..., int] = default_choose_buy_qty,
    allocate_buy_quantities_fn: Callable[..., dict[str, int]] = default_allocate_buy_quantities,
    get_default_book_fn: Callable[..., Any] = get_default_book,
    feature_provider: FeatureDataProvider | None = None,
) -> BacktestResult:
    account = get_account_fn(conn, cfg.account_name)
    # Execution settings are book-owned (revision 0004): the account's default
    # book supplies the risk/sizing knobs the simulation runs under.
    default_book = get_default_book_fn(conn, account_id=row_expect_int(account, "id"))
    start_date, end_date = resolve_backtest_dates_fn(cfg.start, cfg.end, cfg.lookback_months)
    warnings = warnings_for_config_fn(default_book, cfg.allow_approximate_leaps)

    # Optional indicator warm-up: pull extra history before the scoring window so
    # signals are warm at the window start. Only price history reaches back this far;
    # scoring (returns/trades/snapshots) still starts at start_date.
    warmup_months = getattr(cfg, "warmup_months", 0) or 0
    data_start_date = shift_months(start_date, -warmup_months) if warmup_months > 0 else start_date

    default_tickers, month_to_tickers, all_tickers, universe_warnings = resolve_universe_fn(
        cfg,
        start_date,
        end_date,
    )
    warnings.extend(universe_warnings)

    # Bars, not closes: the panel keeps each ticker's full range available for
    # indicators, while `close` stays the endpoint view the simulation prices at.
    panel = build_bar_panel(cast(Any, fetch_bar_history_fn(all_tickers, data_start_date, end_date)), all_tickers)
    close = panel.close
    if len(close.index) < 3:
        raise ValueError("Not enough historical bars in selected range. Need at least 3 trading days.")

    benchmark_ticker = row_expect_str(account, "benchmark_ticker")
    account_id = row_expect_int(account, "id")
    initial_cash = row_expect_float(account, "initial_cash")
    # An explicit override backtests a specific strategy (e.g. a rotation
    # challenger); otherwise the account's active strategy is used.
    strategy_override = getattr(cfg, "strategy", None)
    strategy_name = (
        strategy_override.strip()
        if strategy_override and strategy_override.strip()
        else active_strategy_for_account(conn, account_id)
    )
    strategy_spec = resolve_strategy(strategy_name)
    # A param override (walk-forward optimizer candidates) is merged over the
    # strategy's catalog defaults for this run only; the catalog is never mutated.
    param_override = getattr(cfg, "param_override", None)
    effective_params = (
        strategy_spec.default_params if not param_override else {**strategy_spec.default_params, **param_override}
    )

    # The strategy's declared indicators, computed once per ticker for the whole
    # run. Deriving them inside the signal would recompute the same rolling
    # windows on every bar to keep only their last value.
    ticker_closes = {ticker: panel.frame(ticker)[BAR_CLOSE].to_numpy(dtype=float) for ticker in all_tickers}
    ticker_indicators = {
        ticker: build_indicator_arrays(panel.frame(ticker), strategy_spec.indicators, effective_params)
        for ticker in all_tickers
    }
    ticker_priced_bars = {ticker: count_priced_bars(closes) for ticker, closes in ticker_closes.items()}

    benchmark_series = fetch_benchmark_close_fn(benchmark_ticker, start_date, end_date)

    feature_bundle = None
    if strategy_spec.required_features:
        active_feature_provider = require_feature_provider(feature_provider)
        feature_bundle = active_feature_provider.build_feature_bundle(all_tickers, start_date, end_date, close)
        warnings.extend(feature_bundle.warnings)

    # Wrap the header, first snapshot, and the simulate/persist loop in one
    # unit_of_work so an interrupted run leaves no partial result tree. All
    # external data was fetched above; this transaction covers only in-memory
    # simulation and its writes, never network I/O.
    with unit_of_work(conn):
        # Pass the canonical strategy key: backtest_runs stores a strategies FK,
        # so aliases/display names must resolve to the seeded catalog key first.
        run_id = insert_run_fn(conn, account_id, strategy_spec.strategy_id, start_date, end_date, cfg, warnings)

        state = _PortfolioState(cash=initial_cash)
        ctx = _ExecutionContext(
            conn=conn,
            run_id=run_id,
            cfg=cfg,
            slippage_multiplier_buy=1.0 + (cfg.slippage_bps / BASIS_POINTS_DIVISOR),
            slippage_multiplier_sell=1.0 - (cfg.slippage_bps / BASIS_POINTS_DIVISOR),
            insert_trade_fn=insert_trade_fn,
            choose_buy_qty_fn=choose_buy_qty_fn,
            allocate_buy_quantities_fn=allocate_buy_quantities_fn,
            default_book=default_book,
        )
        positions = state.positions

        equity_curve: list[float] = []

        dates = list(close.index)
        # Warm-up bars (before start_date) only initialize indicator history; scoring
        # begins at the first bar within the window so returns exclude the lead-in.
        # With no warm-up, scoring starts at bar zero — identical to the original path.
        if warmup_months > 0:
            scoring_idx = _first_scoring_index(dates, start_date)
            if len(dates) - scoring_idx < 2:
                raise ValueError("Not enough trading days in the scoring window after warm-up.")
        else:
            scoring_idx = 0

        first_prices = {ticker: float(close.loc[dates[scoring_idx], ticker]) for ticker in all_tickers}
        first_mv = compute_market_value(positions, first_prices)
        first_equity = state.cash + first_mv
        insert_snapshot_fn(
            conn,
            run_id,
            dates[scoring_idx].date().isoformat(),
            state.cash,
            first_mv,
            first_equity,
            state.realized_pnl,
            0.0,
        )
        equity_curve.append(first_equity)

        for idx in range(scoring_idx + 1, len(dates)):
            signal_date = dates[idx - 1]
            trade_date = dates[idx]

            trade_prices = close.loc[trade_date]
            month_key = f"{signal_date.year:04d}-{signal_date.month:02d}"
            active_tickers = month_to_tickers.get(month_key, default_tickers)
            held_tickers = [ticker for ticker, qty in positions.items() if qty > 0]
            strategy_tickers = sorted(set(active_tickers) | set(held_tickers))

            # A bar resolves in three phases: decide, then sell, then buy. Deciding
            # first keeps every signal a function of the same pre-trade state.
            # Selling before buying makes the day's proceeds available to every
            # buy rather than only to tickers later in the iteration order.
            signals = {}
            for ticker in strategy_tickers:
                feature_history = (
                    None if feature_bundle is None else feature_bundle.history_for_ticker(ticker, signal_date)
                )
                view = IndicatorView(
                    closes=ticker_closes[ticker],
                    indicators=ticker_indicators[ticker],
                    index=idx - 1,
                    priced_bars=ticker_priced_bars[ticker],
                )
                signals[ticker] = evaluate_signal(strategy_name, view, effective_params, feature_history)

            _execute_sells(
                ctx,
                state,
                trade_date=trade_date,
                trade_prices=trade_prices,
                signals=signals,
                tickers=strategy_tickers,
            )
            _execute_buys(
                ctx,
                state,
                trade_date=trade_date,
                trade_prices=trade_prices,
                signals=signals,
                tickers=strategy_tickers,
                active_tickers=active_tickers,
            )

            marks = {ticker: float(trade_prices[ticker]) for ticker in all_tickers}
            market_value = compute_market_value(positions, marks)
            unrealized_pnl = compute_unrealized_pnl(positions, state.avg_cost, marks)

            equity = state.cash + market_value
            equity_curve.append(equity)
            insert_snapshot_fn(
                conn,
                run_id,
                trade_date.date().isoformat(),
                state.cash,
                market_value,
                equity,
                state.realized_pnl,
                unrealized_pnl,
            )

    ending_equity = equity_curve[-1]
    total_return_pct = ((ending_equity / initial_cash) - 1.0) * 100.0
    benchmark_return = benchmark_return_pct(benchmark_series, initial_cash)
    alpha_pct = None if benchmark_return is None else total_return_pct - benchmark_return
    performance = summarize_backtest_performance(equity_curve, state.executed_trades)

    return BacktestResult(
        run_id=run_id,
        account_name=cfg.account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        tickers=all_tickers,
        trade_count=state.trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return,
        alpha_pct=alpha_pct,
        max_drawdown_pct=max_drawdown_pct(equity_curve),
        annualized_return_pct=performance.annualized_return_pct,
        sharpe_ratio=performance.sharpe_ratio,
        sortino_ratio=performance.sortino_ratio,
        calmar_ratio=performance.calmar_ratio,
        win_rate_pct=performance.win_rate_pct,
        profit_factor=performance.profit_factor,
        avg_trade_return_pct=performance.avg_trade_return_pct,
        warnings=warnings,
    )
