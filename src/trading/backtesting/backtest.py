from __future__ import annotations

import sqlite3
from datetime import date

from infrastructure.market_data.factory import build_provider
from trading.backtesting.domain.risk_warnings import build_backtest_warnings
from trading.backtesting.models import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
)
from trading.backtesting.report_models import BacktestFullReport, BacktestLeaderboardEntry, BacktestReportSummary
from trading.backtesting.repositories.backtest_repository import (
    insert_backtest_run,
    insert_backtest_snapshot,
    insert_backtest_trade,
)
from trading.backtesting.services import (
    build_monthly_universe,
    fetch_backtest_leaderboard_entries,
    fetch_backtest_report_data,
    fetch_benchmark_close,
    fetch_close_history,
    load_tickers_from_file,
    resolve_backtest_dates,
    run_backtest as run_backtest_impl,
)
from trading.domain.auto_trading_policy import choose_buy_qty
from trading.domain.strategies.resolution import resolve_strategy
from trading.models.books.book_record import BookRecord
from trading.repositories.books import BookRepository
from trading.services.accounts import get_account
from trading.services.market_data import build_feature_provider


def _warnings_for_config(book: BookRecord | None, allow_approximate_leaps: bool) -> list[str]:
    # Execution settings are book-owned (revision 0004); the account's default
    # book carries the settings a backtest simulates under.
    return build_backtest_warnings(
        risk_policy=book.risk_policy if book is not None else None,
        instrument_mode=book.instrument_mode if book is not None else None,
        allow_approximate_leaps=allow_approximate_leaps,
    )


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
    default_book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    warnings = _warnings_for_config(default_book, cfg.allow_approximate_leaps)

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


def _noop_insert_run(*_args: object, **_kwargs: object) -> int:
    return 0


def _noop_insert_trade(*_args: object, **_kwargs: object) -> None:
    return None


def _noop_insert_snapshot(*_args: object, **_kwargs: object) -> None:
    return None


def _run_backtest(conn: sqlite3.Connection, cfg: BacktestConfig, *, persist: bool) -> BacktestResult:
    # Composition seam: build the market-data + feature providers once for the
    # run and inject them down the data path (no global access inside services).
    # When persist is False the run computes metrics only (no run/trade/snapshot
    # rows) — used by the walk-forward optimizer for training-candidate trials.
    provider = build_provider()
    feature_provider = build_feature_provider(market_data_provider=provider)
    return run_backtest_impl(
        conn,
        cfg,
        get_account_fn=get_account,
        resolve_backtest_dates_fn=resolve_backtest_dates,
        warnings_for_config_fn=_warnings_for_config,
        resolve_universe_fn=_resolve_universe,
        fetch_close_history_fn=lambda tickers, start_date, end_date: fetch_close_history(
            tickers, start_date, end_date, provider=provider
        ),
        fetch_benchmark_close_fn=lambda benchmark_ticker, start_date, end_date: fetch_benchmark_close(
            benchmark_ticker, start_date, end_date, provider=provider
        ),
        insert_run_fn=_insert_run if persist else _noop_insert_run,
        insert_trade_fn=_insert_trade if persist else _noop_insert_trade,
        insert_snapshot_fn=_insert_snapshot if persist else _noop_insert_snapshot,
        choose_buy_qty_fn=choose_buy_qty,
        feature_provider=feature_provider,
    )


def run_backtest(conn: sqlite3.Connection, cfg: BacktestConfig) -> BacktestResult:
    return _run_backtest(conn, cfg, persist=True)


def run_backtest_metrics_only(conn: sqlite3.Connection, cfg: BacktestConfig) -> BacktestResult:
    """Run a simulation and return its metrics without persisting any run, trade, or
    snapshot rows. Lets the walk-forward optimizer evaluate grid candidates on training
    windows without polluting stored backtest evidence."""
    return _run_backtest(conn, cfg, persist=False)


def backtest_report_full(conn: sqlite3.Connection, run_id: int) -> BacktestFullReport:
    return fetch_backtest_report_data(conn, run_id=run_id)


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
