from __future__ import annotations

import math
import sqlite3
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

import pandas as pd

from common.market_data import get_feature_provider
from trading.accounts import get_account, utc_now_iso
from trading.features.backtesting.backtest_data import (
    build_monthly_universe,
    fetch_benchmark_close,
    fetch_close_history,
    load_tickers_from_file,
    resolve_backtest_dates,
)
from trading.database.code.db_coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_str
from trading.rotation import resolve_active_strategy
from trading.features.backtesting.strategy_signals import resolve_signal, resolve_strategy


@dataclass
class BacktestConfig:
    account_name: str
    tickers_file: str
    universe_history_dir: str | None
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


@dataclass
class WalkForwardConfig:
    account_name: str
    tickers_file: str
    universe_history_dir: str | None
    start: str | None
    end: str | None
    lookback_months: int | None
    test_months: int
    step_months: int
    slippage_bps: float
    fee_per_trade: float
    run_name_prefix: str | None
    allow_approximate_leaps: bool


@dataclass
class WalkForwardSummary:
    account_name: str
    start_date: str
    end_date: str
    window_count: int
    run_ids: list[int]
    average_return_pct: float
    median_return_pct: float
    best_return_pct: float
    worst_return_pct: float


@dataclass
class BacktestBatchConfig:
    account_names: list[str]
    tickers_file: str
    universe_history_dir: str | None
    start: str | None
    end: str | None
    lookback_months: int | None
    slippage_bps: float
    fee_per_trade: float
    run_name_prefix: str | None
    allow_approximate_leaps: bool


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


def _add_months(base: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be >= 0")

    month_index = (base.year * 12 + (base.month - 1)) + months
    target_year = month_index // 12
    target_month = (month_index % 12) + 1
    target_day = min(base.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def build_walk_forward_windows(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> list[tuple[date, date]]:
    if test_months <= 0:
        raise ValueError("test_months must be > 0")
    if step_months <= 0:
        raise ValueError("step_months must be > 0")
    if start_date >= end_date:
        raise ValueError("start_date must be before end_date")

    windows: list[tuple[date, date]] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        next_cursor = _add_months(cursor, test_months)
        window_start = max(start_date, cursor)
        window_end = min(end_date, next_cursor - timedelta(days=1))
        if window_start < window_end:
            windows.append((window_start, window_end))
        cursor = _add_months(cursor, step_months)

    return windows


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

    risk_policy = row_str(account, "risk_policy")
    if risk_policy in {"fixed_stop", "take_profit", "stop_and_target"}:
        warnings.append(
            "Stop-loss/take-profit checks are approximated on daily closes and can differ from intraday execution."
        )

    if row_str(account, "instrument_mode") == "leaps":
        warnings.append(
            "LEAPs mode is approximated using underlying equity prices; options chain history and Greeks are not modeled."
        )
        if not allow_approximate_leaps:
            warnings.append(
                "LEAPs approximation opt-in was not enabled; proceeding with approximate LEAPs assumptions for research only."
            )
    return warnings


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
    total = 0.0
    for ticker, qty in positions.items():
        if qty <= 0:
            continue
        total += (marks[ticker] - avg_cost[ticker]) * qty
    return total


def _normalize_benchmark_series(benchmark_close: pd.Series | pd.DataFrame) -> pd.Series:
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

    normalized = pd.to_numeric(series, errors="coerce").dropna()
    return normalized


def _benchmark_return_pct(benchmark_close: pd.Series | pd.DataFrame, initial_cash: float) -> float | None:
    series = _normalize_benchmark_series(benchmark_close)
    if len(series) < 2:
        return None

    start_px = float(series.iloc[0])
    end_px = float(series.iloc[-1])
    if start_px <= 0:
        return None

    equity = initial_cash * (end_px / start_px)
    return ((equity / initial_cash) - 1.0) * 100.0


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
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            strategy_name,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            strategy_name,
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
    assert cursor.lastrowid is not None
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
    run = conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
             r.tickers_file, r.notes, r.warnings, a.name AS account_name,
             COALESCE(r.strategy_name, a.strategy) AS strategy,
             a.benchmark_ticker
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
        ORDER BY snapshot_time ASC
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
        raise ValueError(f"No snapshots found for backtest run {run_id}")

    first_equity = row_expect_float(snapshots[0], "equity")
    last_equity = row_expect_float(snapshots[-1], "equity")

    equity_curve = [row_float(r, "equity") for r in snapshots]
    max_drawdown = _max_drawdown_pct([e for e in equity_curve if e is not None])

    report_run_id = row_expect_int(run, "id")
    slippage_bps = row_expect_float(run, "slippage_bps")
    fee_per_trade = row_expect_float(run, "fee_per_trade")

    return {
        "run_id": report_run_id,
        "run_name": run["run_name"],
        "account_name": run["account_name"],
        "strategy": run["strategy"],
        "benchmark_ticker": run["benchmark_ticker"],
        "start_date": run["start_date"],
        "end_date": run["end_date"],
        "created_at": run["created_at"],
        "slippage_bps": slippage_bps,
        "fee_per_trade": fee_per_trade,
        "tickers_file": run["tickers_file"],
        "notes": run["notes"],
        "warnings": run["warnings"],
        "trade_count": len(trades),
        "starting_equity": first_equity,
        "ending_equity": last_equity,
        "total_return_pct": ((last_equity / first_equity) - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown,
        "snapshots": [dict(r) for r in snapshots],
        "trades": [dict(r) for r in trades],
    }


def backtest_leaderboard(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
    account_name: str | None = None,
    strategy: str | None = None,
) -> list[dict[str, object]]:
    if limit <= 0:
        raise ValueError("limit must be > 0")

    query = """
        SELECT
            r.id AS run_id,
            r.run_name,
            r.start_date,
            r.end_date,
            r.created_at,
            a.name AS account_name,
            COALESCE(r.strategy_name, a.strategy) AS strategy,
            a.benchmark_ticker,
            a.initial_cash,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_time ASC, s.id ASC
                LIMIT 1
            ) AS starting_equity,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_time DESC, s.id DESC
                LIMIT 1
            ) AS ending_equity,
            (
                SELECT COUNT(*)
                FROM backtest_trades t
                WHERE t.run_id = r.id
            ) AS trade_count
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE (? IS NULL OR a.name = ?)
                    AND (? IS NULL OR LOWER(COALESCE(r.strategy_name, a.strategy)) LIKE '%' || LOWER(?) || '%')
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
    """
    rows = conn.execute(
        query,
        (account_name, account_name, strategy, strategy, int(limit)),
    ).fetchall()

    entries: list[dict[str, object]] = []
    for row in rows:
        start_equity = row_float(row, "starting_equity")
        end_equity = row_float(row, "ending_equity")
        if start_equity is None or end_equity is None or start_equity <= 0:
            continue

        equity_rows = conn.execute(
            """
            SELECT equity
            FROM backtest_equity_snapshots
            WHERE run_id = ?
            ORDER BY snapshot_time ASC, id ASC
            """,
            (row_expect_int(row, "run_id"),),
        ).fetchall()
        curve = [row_float(item, "equity") for item in equity_rows]
        max_drawdown_pct = _max_drawdown_pct([value for value in curve if value is not None])

        total_return_pct = ((end_equity / start_equity) - 1.0) * 100.0

        benchmark_return_pct: float | None = None
        alpha_pct: float | None = None
        try:
            benchmark_series = fetch_benchmark_close(
                row_expect_str(row, "benchmark_ticker"),
                date.fromisoformat(row_expect_str(row, "start_date")),
                date.fromisoformat(row_expect_str(row, "end_date")),
            )
            benchmark_return_pct = _benchmark_return_pct(
                benchmark_series,
                row_expect_float(row, "initial_cash"),
            )
            if benchmark_return_pct is not None:
                alpha_pct = total_return_pct - benchmark_return_pct
        except Exception:
            benchmark_return_pct = None
            alpha_pct = None

        entries.append(
            {
                "run_id": row_expect_int(row, "run_id"),
                "run_name": row["run_name"],
                "account_name": row_expect_str(row, "account_name"),
                "strategy": row_expect_str(row, "strategy"),
                "start_date": row_expect_str(row, "start_date"),
                "end_date": row_expect_str(row, "end_date"),
                "created_at": row_expect_str(row, "created_at"),
                "trade_count": int(row["trade_count"]),
                "starting_equity": float(start_equity),
                "ending_equity": float(end_equity),
                "total_return_pct": float(total_return_pct),
                "max_drawdown_pct": float(max_drawdown_pct),
                "benchmark_return_pct": benchmark_return_pct,
                "alpha_pct": alpha_pct,
            }
        )

    entries.sort(key=lambda entry: float(entry["total_return_pct"]), reverse=True)
    return entries


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

    if not windows:
        raise ValueError("No walk-forward windows generated for the selected date range.")

    run_ids: list[int] = []
    total_returns: list[float] = []

    for i, (window_start, window_end) in enumerate(windows):
        run_name = None
        if cfg.run_name_prefix:
            run_name = f"{cfg.run_name_prefix}_{i + 1:02d}"

        test_cfg = BacktestConfig(
            account_name=cfg.account_name,
            tickers_file=cfg.tickers_file,
            universe_history_dir=cfg.universe_history_dir,
            start=window_start.isoformat(),
            end=window_end.isoformat(),
            lookback_months=None,
            slippage_bps=cfg.slippage_bps,
            fee_per_trade=cfg.fee_per_trade,
            run_name=run_name,
            allow_approximate_leaps=cfg.allow_approximate_leaps,
        )

        result = run_backtest(conn, test_cfg)
        run_ids.append(result.run_id)
        total_returns.append(result.total_return_pct)

    if not total_returns:
        raise ValueError("No returns were computed.")

    return WalkForwardSummary(
        account_name=cfg.account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        window_count=len(windows),
        run_ids=run_ids,
        average_return_pct=sum(total_returns) / len(total_returns),
        median_return_pct=float(median(total_returns)),
        best_return_pct=max(total_returns),
        worst_return_pct=min(total_returns),
    )
