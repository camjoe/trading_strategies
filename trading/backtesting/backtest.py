from __future__ import annotations

import sqlite3
from datetime import date
from typing import Callable, cast

from common.market_data import get_feature_provider

from common.coercion import (
    row_expect_float,
    row_expect_int,
    row_expect_str,
)
from trading.domain.auto_trader_policy import choose_buy_qty
from trading.backtesting.trading_bridge import (
    get_account,
    resolve_active_strategy,
)
from trading.backtesting.models import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
    WalkForwardConfig,
    WalkForwardSummary,
)
from trading.backtesting.report_models import BacktestFullReport, BacktestLeaderboardEntry, BacktestReportSummary

from trading.backtesting.domain.metrics import benchmark_return_pct, max_drawdown_pct
from trading.backtesting.domain.risk_warnings import build_backtest_warnings
from trading.backtesting.domain.simulation_math import (
    compute_market_value,
    compute_unrealized_pnl,
    update_on_buy,
    update_on_sell,
)
from trading.backtesting.domain.strategy_signals import resolve_signal, resolve_strategy
from trading.backtesting.domain.windowing import build_walk_forward_windows as build_walk_forward_windows_impl
from trading.backtesting.repositories.backtest_repository import (
    insert_backtest_run,
    insert_backtest_snapshot,
    insert_backtest_trade,
)
from trading.backtesting.services import (
    build_monthly_universe,
    execute_walk_forward_backtest,
    fetch_backtest_leaderboard_entries,
    fetch_backtest_report_data,
    fetch_walk_forward_report_data,
    fetch_benchmark_close,
    fetch_close_history,
    load_tickers_from_file,
    resolve_backtest_dates,
    run_backtest as run_backtest_impl,
)


def build_walk_forward_windows(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> list[tuple[date, date]]:
    return build_walk_forward_windows_impl(start_date, end_date, test_months, step_months)


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
    return run_backtest_impl(
        conn,
        cfg,
        get_account_fn=get_account,
        resolve_backtest_dates_fn=resolve_backtest_dates,
        warnings_for_config_fn=_warnings_for_config,
        resolve_universe_fn=_resolve_universe,
        fetch_close_history_fn=fetch_close_history,
        fetch_benchmark_close_fn=fetch_benchmark_close,
        row_expect_str_fn=row_expect_str,
        row_expect_int_fn=row_expect_int,
        row_expect_float_fn=row_expect_float,
        resolve_active_strategy_fn=cast(Callable[[sqlite3.Row], str], resolve_active_strategy),
        resolve_strategy_fn=resolve_strategy,
        get_feature_provider_fn=get_feature_provider,
        insert_run_fn=_insert_run,
        compute_market_value_fn=compute_market_value,
        compute_unrealized_pnl_fn=compute_unrealized_pnl,
        update_on_buy_fn=update_on_buy,
        update_on_sell_fn=update_on_sell,
        insert_trade_fn=_insert_trade,
        insert_snapshot_fn=_insert_snapshot,
        resolve_signal_fn=resolve_signal,
        choose_buy_qty_fn=choose_buy_qty,
        benchmark_return_pct_fn=benchmark_return_pct,
        max_drawdown_pct_fn=max_drawdown_pct,
        backtest_result_cls=BacktestResult,
    )


def backtest_report_full(conn: sqlite3.Connection, run_id: int) -> BacktestFullReport:
    return fetch_backtest_report_data(conn, run_id=run_id, fetch_benchmark_close_fn=fetch_benchmark_close)


def backtest_report(conn: sqlite3.Connection, run_id: int) -> dict[str, object]:
    return backtest_report_full(conn, run_id).to_payload()


def backtest_report_summary(conn: sqlite3.Connection, run_id: int) -> BacktestReportSummary:
    return backtest_report_full(conn, run_id).summary


def _validated_strategy_filter(strategy: str | None) -> str | None:
    if strategy is None:
        return None
    strategy_name = strategy.strip()
    if not strategy_name:
        return None
    resolve_strategy(strategy_name)
    return strategy_name


def backtest_leaderboard(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
    account_name: str | None = None,
    strategy: str | None = None,
) -> list[dict[str, object]]:
    strategy_filter = _validated_strategy_filter(strategy)
    rows: list[dict[str, object]] = []
    for entry, starting_equity in _fetch_backtest_leaderboard_entries(
        conn,
        limit=limit,
        account_name=account_name,
        strategy=strategy_filter,
    ):
        row: dict[str, object] = {
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
            "sharpe_ratio": entry.sharpe_ratio,
            "sortino_ratio": entry.sortino_ratio,
            "calmar_ratio": entry.calmar_ratio,
            "win_rate_pct": entry.win_rate_pct,
            "profit_factor": entry.profit_factor,
            "avg_trade_return_pct": entry.avg_trade_return_pct,
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
    strategy_filter = _validated_strategy_filter(strategy)
    return [
        entry
        for entry, _starting_equity in _fetch_backtest_leaderboard_entries(
            conn,
            limit=limit,
            account_name=account_name,
            strategy=strategy_filter,
        )
    ]


def _fetch_backtest_leaderboard_entries(
    conn: sqlite3.Connection,
    *,
    limit: int,
    account_name: str | None,
    strategy: str | None,
) -> list[tuple[BacktestLeaderboardEntry, float]]:
    return fetch_backtest_leaderboard_entries(
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


def walk_forward_report(
    conn: sqlite3.Connection,
    *,
    group_id: int | None = None,
    account_name: str | None = None,
    strategy_name: str | None = None,
) -> dict[str, object]:
    return fetch_walk_forward_report_data(
        conn,
        group_id=group_id,
        account_name=account_name,
        strategy_name=strategy_name,
    ).to_payload()
