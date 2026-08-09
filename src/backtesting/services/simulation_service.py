from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, cast

import pandas as pd

from backtesting.domain.bars import build_bar_panel
from backtesting.domain.metrics import benchmark_return_pct, max_drawdown_pct, summarize_backtest_performance
from backtesting.domain.risk_warnings import build_backtest_warnings
from backtesting.domain.simulation_math import (
    compute_market_value,
    compute_unrealized_pnl,
    update_on_buy,
    update_on_sell,
)
from backtesting.domain.windowing import shift_months
from backtesting.models import BacktestConfig, BacktestResult
from backtesting.repositories.runs import insert_run, insert_snapshot, insert_trade
from backtesting.services.backtest_data_service import resolve_backtest_dates, resolve_universe
from common.constants import BASIS_POINTS_DIVISOR
from trading.domain.auto_trading_policy import allocate_buy_quantities, choose_buy_qty
from trading.domain.strategies.indicator_view import (
    IndicatorView,
    build_signal_inputs,
)
from trading.domain.strategies.resolution import evaluate_signal, resolve_strategy
from trading.models.books import BookRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.services.accounts import get_account
from trading.services.books.book_assignments import active_strategy_for_account, get_default_book
from trading.services.market_data import FeatureDataProvider, require_feature_provider


def _warnings_for_config(book: BookRecord | None, allow_approximate_leaps: bool) -> list[str]:
    # Execution settings are book-owned (revision 0004); the account's default
    # book carries the settings a backtest simulates under.
    return build_backtest_warnings(
        risk_policy=book.risk_policy if book is not None else None,
        instrument_mode=book.instrument_mode if book is not None else None,
        allow_approximate_leaps=allow_approximate_leaps,
    )


def preview_backtest_warnings(conn: sqlite3.Connection, cfg: BacktestConfig) -> list[str]:
    """The warnings a run under this config would raise, without running it.

    Resolves the same book settings and universe the run would, so a preview and
    the run it precedes cannot disagree about what they warn on.
    """
    account = get_account(conn, cfg.account_name)
    default_book = get_default_book(conn, account_id=account.id)
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)

    warnings = _warnings_for_config(default_book, cfg.allow_approximate_leaps)
    universe = resolve_universe(
        tickers_file=cfg.tickers_file,
        universe_history_dir=cfg.universe_history_dir,
        start_date=start_date,
        end_date=end_date,
    )
    warnings.extend(universe.warnings)
    return warnings


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
    persist: bool
    default_book: Any
    all_tickers: list[str]
    default_tickers: list[str]
    month_to_tickers: dict[str, list[str]]
    signal_inputs: dict[str, Any]
    strategy_name: str
    effective_params: dict[str, Any]
    feature_bundle: Any


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
    if ctx.persist:
        insert_trade(
            ctx.conn,
            run_id=ctx.run_id,
            trade_time=trade_date.date().isoformat(),
            ticker=ticker,
            side=side,
            qty=qty,
            price=exec_px,
            fee=ctx.cfg.fee_per_trade,
            slippage_bps=ctx.cfg.slippage_bps,
            note=note,
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
        requested_qty = choose_buy_qty(
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

    granted = allocate_buy_quantities(sized_buys, cash=state.cash, fee_per_trade=ctx.cfg.fee_per_trade)
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


def _evaluate_signals(
    ctx: _ExecutionContext,
    tickers: list[str],
    *,
    signal_date: Any,
    signal_index: int,
) -> dict[str, str]:
    """Each ticker's decision for the coming bar, read off the signal bar's state."""
    signals: dict[str, str] = {}
    for ticker in tickers:
        feature_history = (
            None if ctx.feature_bundle is None else ctx.feature_bundle.history_for_ticker(ticker, signal_date)
        )
        closes, indicators, priced_bars = ctx.signal_inputs[ticker]
        view = IndicatorView(
            closes=closes,
            indicators=indicators,
            index=signal_index,
            priced_bars=priced_bars,
        )
        signals[ticker] = evaluate_signal(ctx.strategy_name, view, ctx.effective_params, feature_history)
    return signals


def _record_snapshot(
    ctx: _ExecutionContext,
    state: _PortfolioState,
    *,
    snapshot_date: Any,
    market_value: float,
    equity: float,
    unrealized_pnl: float,
) -> None:
    if not ctx.persist:
        return
    insert_snapshot(
        ctx.conn,
        run_id=ctx.run_id,
        snapshot_time=snapshot_date.date().isoformat(),
        cash=state.cash,
        market_value=market_value,
        equity=equity,
        realized_pnl=state.realized_pnl,
        unrealized_pnl=unrealized_pnl,
    )


def _simulate_bars(
    ctx: _ExecutionContext,
    state: _PortfolioState,
    *,
    close: pd.DataFrame,
    dates: list,
    scoring_idx: int,
) -> list[float]:
    """Advance the portfolio one bar at a time and return the equity curve.

    Opens on the scoring bar's mark, then resolves each later bar in three phases:
    decide, sell, buy. Deciding first keeps every signal a function of the same
    pre-trade state; selling before buying makes the day's proceeds available to
    every buy rather than only to tickers later in the iteration order.
    """
    first_prices = {ticker: float(close.loc[dates[scoring_idx], ticker]) for ticker in ctx.all_tickers}
    first_mv = compute_market_value(state.positions, first_prices)
    first_equity = state.cash + first_mv
    _record_snapshot(
        ctx,
        state,
        snapshot_date=dates[scoring_idx],
        market_value=first_mv,
        equity=first_equity,
        unrealized_pnl=0.0,
    )
    equity_curve: list[float] = [first_equity]

    for index in range(scoring_idx + 1, len(dates)):
        signal_date = dates[index - 1]
        trade_date = dates[index]
        trade_prices = close.loc[trade_date]

        month_key = f"{signal_date.year:04d}-{signal_date.month:02d}"
        active_tickers = ctx.month_to_tickers.get(month_key, ctx.default_tickers)
        held_tickers = [ticker for ticker, qty in state.positions.items() if qty > 0]
        strategy_tickers = sorted(set(active_tickers) | set(held_tickers))

        signals = _evaluate_signals(ctx, strategy_tickers, signal_date=signal_date, signal_index=index - 1)
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

        marks = {ticker: float(trade_prices[ticker]) for ticker in ctx.all_tickers}
        market_value = compute_market_value(state.positions, marks)
        equity = state.cash + market_value
        _record_snapshot(
            ctx,
            state,
            snapshot_date=trade_date,
            market_value=market_value,
            equity=equity,
            unrealized_pnl=compute_unrealized_pnl(state.positions, state.avg_cost, marks),
        )
        equity_curve.append(equity)

    return equity_curve


def _first_scoring_index(dates: list, scoring_start: date) -> int:
    """Index of the first loaded bar that falls on/after the scoring window start.
    Earlier bars are warm-up history. With no warm-up this is 0 (bar zero)."""
    for index, timestamp in enumerate(dates):
        if timestamp.date() >= scoring_start:
            return index
    raise ValueError("No trading days fall within the scoring window.")


@dataclass(frozen=True)
class _RunInputs:
    """Everything resolved before the first bar: the window, the universe, the
    strategy and its precomputed indicators, and the frozen benchmark return."""

    account_id: int
    initial_cash: float
    benchmark_ticker: str
    benchmark_return: float | None
    start_date: date
    end_date: date
    warmup_months: int
    warnings: list[str]
    close: pd.DataFrame
    default_book: Any
    all_tickers: list[str]
    default_tickers: list[str]
    month_to_tickers: dict[str, list[str]]
    strategy_key: str
    strategy_name: str
    effective_params: dict[str, Any]
    signal_inputs: dict[str, Any]
    feature_bundle: Any


def _resolve_strategy_inputs(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    account_id: int,
    panel: Any,
    all_tickers: list[str],
) -> tuple[Any, str, dict[str, Any], dict[str, Any]]:
    """The strategy this run simulates, its effective parameters, and its
    indicators precomputed once per ticker."""
    # An explicit override backtests a specific strategy (e.g. a rotation
    # challenger); otherwise the account's active strategy is used.
    strategy_override = cfg.strategy
    strategy_name = (
        strategy_override.strip()
        if strategy_override and strategy_override.strip()
        else active_strategy_for_account(conn, account_id)
    )
    strategy_spec = resolve_strategy(strategy_name)
    # A param override (walk-forward optimizer candidates) is merged over the
    # strategy's catalog defaults for this run only; the catalog is never mutated.
    param_override = cfg.param_override
    effective_params = (
        strategy_spec.default_params if not param_override else {**strategy_spec.default_params, **param_override}
    )

    # Computed once for the whole run: deriving indicators inside the signal would
    # recompute the same rolling windows on every bar to keep only their last value.
    #
    # Computed from each ticker's own bars (`panel.source`), not from its
    # calendar-aligned frame, then carried onto the shared calendar — otherwise a
    # ticker's indicators depend on which other tickers share the run. The
    # simulation still prices and marks off the aligned frame, which needs a value
    # on every bar.
    calendar = pd.DatetimeIndex(panel.dates)
    signal_inputs = {
        ticker: build_signal_inputs(
            panel.source(ticker), strategy_spec.indicators, effective_params, calendar=calendar
        )
        for ticker in all_tickers
    }
    return strategy_spec, strategy_name, effective_params, signal_inputs


def _resolve_run_inputs(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    fetch_bar_history_fn: Callable[..., Mapping[str, Any]],
    fetch_benchmark_close_fn: Callable[..., object],
    feature_provider: FeatureDataProvider | None,
) -> _RunInputs:
    """Resolve the run's inputs and fetch its market data.

    Every external read the run needs happens here, before the write transaction
    opens, so that transaction covers only in-memory simulation and its writes.
    """
    account = get_account(conn, cfg.account_name)
    # Execution settings are book-owned (revision 0004): the account's default
    # book supplies the risk/sizing knobs the simulation runs under.
    default_book = get_default_book(conn, account_id=account.id)
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    warnings = _warnings_for_config(default_book, cfg.allow_approximate_leaps)

    # Optional indicator warm-up: pull extra history before the scoring window so
    # signals are warm at the window start. Only price history reaches back this far;
    # scoring (returns/trades/snapshots) still starts at start_date.
    warmup_months = cfg.warmup_months or 0
    data_start_date = shift_months(start_date, -warmup_months) if warmup_months > 0 else start_date

    universe = resolve_universe(
        tickers_file=cfg.tickers_file,
        universe_history_dir=cfg.universe_history_dir,
        start_date=start_date,
        end_date=end_date,
    )
    default_tickers, month_to_tickers, all_tickers = (
        universe.default_tickers,
        universe.month_to_tickers,
        universe.all_tickers,
    )
    warnings.extend(universe.warnings)

    # Bars, not closes: the panel keeps each ticker's full range available for
    # indicators, while `close` stays the endpoint view the simulation prices at.
    panel = build_bar_panel(cast(Any, fetch_bar_history_fn(all_tickers, data_start_date, end_date)), all_tickers)
    close = panel.close
    if len(close.index) < 3:
        raise ValueError("Not enough historical bars in selected range. Need at least 3 trading days.")

    benchmark_ticker = account.benchmark_ticker
    account_id = account.id
    initial_cash = account.initial_cash
    strategy_spec, strategy_name, effective_params, signal_inputs = _resolve_strategy_inputs(
        conn,
        cfg,
        account_id=account_id,
        panel=panel,
        all_tickers=all_tickers,
    )

    benchmark_series = fetch_benchmark_close_fn(benchmark_ticker, start_date, end_date)
    # Frozen onto the run row below rather than left for readers to recompute: this
    # is the only point where the provider and the run's own benchmark ticker are
    # both in hand.
    benchmark_return = benchmark_return_pct(benchmark_series, initial_cash)

    feature_bundle = None
    if strategy_spec.required_features:
        active_feature_provider = require_feature_provider(feature_provider)
        feature_bundle = active_feature_provider.build_feature_bundle(all_tickers, start_date, end_date, close)
        warnings.extend(feature_bundle.warnings)

    return _RunInputs(
        account_id=account_id,
        initial_cash=initial_cash,
        benchmark_ticker=benchmark_ticker,
        benchmark_return=benchmark_return,
        start_date=start_date,
        end_date=end_date,
        warmup_months=warmup_months,
        warnings=warnings,
        close=close,
        default_book=default_book,
        all_tickers=all_tickers,
        default_tickers=default_tickers,
        month_to_tickers=month_to_tickers,
        # backtest_runs stores a strategies FK, so aliases and display names must
        # resolve to the seeded catalog key before the header is written.
        strategy_key=strategy_spec.strategy_id,
        strategy_name=strategy_name,
        effective_params=effective_params,
        signal_inputs=signal_inputs,
        feature_bundle=feature_bundle,
    )


def _scoring_start_index(dates: list, inputs: _RunInputs) -> int:
    """Where scoring begins: bar zero, or the first bar inside the window when
    warm-up history was loaded ahead of it."""
    if inputs.warmup_months <= 0:
        return 0
    scoring_idx = _first_scoring_index(dates, inputs.start_date)
    if len(dates) - scoring_idx < 2:
        raise ValueError("Not enough trading days in the scoring window after warm-up.")
    return scoring_idx


def run_backtest(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    fetch_bar_history_fn: Callable[..., Mapping[str, Any]],
    fetch_benchmark_close_fn: Callable[..., object],
    persist: bool = True,
    feature_provider: FeatureDataProvider | None = None,
) -> BacktestResult:
    """Simulate one backtest over the configured window and return its metrics.

    The two fetch callables and ``feature_provider`` are the market-data seam: the
    composition root binds a concrete provider into them, so nothing here reaches
    for one itself.

    With ``persist=False`` no run, execution, or snapshot row is written and the
    result carries ``run_id=0``; the walk-forward optimizer evaluates training
    candidates that way so a grid search leaves no stored evidence behind.
    """
    inputs = _resolve_run_inputs(
        conn,
        cfg,
        fetch_bar_history_fn=fetch_bar_history_fn,
        fetch_benchmark_close_fn=fetch_benchmark_close_fn,
        feature_provider=feature_provider,
    )

    # Wrap the header, first snapshot, and the simulate/persist loop in one
    # unit_of_work so an interrupted run leaves no partial result tree. All
    # external data was fetched above; this transaction covers only in-memory
    # simulation and its writes, never network I/O.
    with unit_of_work(conn):
        run_id = (
            insert_run(
                conn,
                account_id=inputs.account_id,
                strategy_name=inputs.strategy_key,
                start_date=inputs.start_date,
                end_date=inputs.end_date,
                cfg=cfg,
                warnings=inputs.warnings,
                benchmark_ticker=inputs.benchmark_ticker,
                benchmark_return_pct=inputs.benchmark_return,
            )
            if persist
            else 0
        )

        state = _PortfolioState(cash=inputs.initial_cash)
        ctx = _ExecutionContext(
            conn=conn,
            run_id=run_id,
            cfg=cfg,
            slippage_multiplier_buy=1.0 + (cfg.slippage_bps / BASIS_POINTS_DIVISOR),
            slippage_multiplier_sell=1.0 - (cfg.slippage_bps / BASIS_POINTS_DIVISOR),
            persist=persist,
            default_book=inputs.default_book,
            all_tickers=inputs.all_tickers,
            default_tickers=inputs.default_tickers,
            month_to_tickers=inputs.month_to_tickers,
            signal_inputs=inputs.signal_inputs,
            strategy_name=inputs.strategy_name,
            effective_params=inputs.effective_params,
            feature_bundle=inputs.feature_bundle,
        )

        dates = list(inputs.close.index)
        equity_curve = _simulate_bars(
            ctx,
            state,
            close=inputs.close,
            dates=dates,
            scoring_idx=_scoring_start_index(dates, inputs),
        )

    ending_equity = equity_curve[-1]
    total_return_pct = ((ending_equity / inputs.initial_cash) - 1.0) * 100.0
    performance = summarize_backtest_performance(equity_curve, state.executed_trades)

    return BacktestResult(
        run_id=run_id,
        account_name=cfg.account_name,
        start_date=inputs.start_date.isoformat(),
        end_date=inputs.end_date.isoformat(),
        tickers=inputs.all_tickers,
        trade_count=state.trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=inputs.benchmark_return,
        alpha_pct=None if inputs.benchmark_return is None else total_return_pct - inputs.benchmark_return,
        max_drawdown_pct=max_drawdown_pct(equity_curve),
        annualized_return_pct=performance.annualized_return_pct,
        sharpe_ratio=performance.sharpe_ratio,
        sortino_ratio=performance.sortino_ratio,
        calmar_ratio=performance.calmar_ratio,
        win_rate_pct=performance.win_rate_pct,
        profit_factor=performance.profit_factor,
        avg_trade_return_pct=performance.avg_trade_return_pct,
        warnings=inputs.warnings,
    )
