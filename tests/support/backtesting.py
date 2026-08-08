from __future__ import annotations

import pandas as pd

from backtesting.backtest import BacktestConfig
from backtesting.models import BacktestResult
from backtesting.models.report import BacktestFullReport, BacktestLeaderboardEntry, BacktestReportSummary
from trading.models import AccountConfig
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME
from trading.services.accounts import create_account


def make_fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def bar_frame(closes: pd.Series) -> pd.DataFrame:
    """One ticker's closes as a bar frame, with high and low equal to the close.

    For tests whose subject is not the bar range: a flat bar makes a
    high/low-reading strategy see exactly what a close-only history showed.
    """
    return pd.DataFrame(
        {
            BAR_OPEN: closes.shift(1).fillna(closes.iloc[0] if len(closes) else 0.0),
            BAR_HIGH: closes,
            BAR_LOW: closes,
            BAR_CLOSE: closes,
            BAR_VOLUME: pd.Series(1_000_000.0, index=closes.index),
        }
    )[list(BAR_COLUMNS)]


def bars_from_closes(closes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Wrap a ticker-per-column close frame as per-ticker bar frames.

    For tests whose subject is the simulation rather than the bar data: the
    close column drives everything as before, and open/high/low are derived so
    the OHLC invariants hold.
    """
    frames: dict[str, pd.DataFrame] = {}
    for ticker in closes.columns:
        close = closes[ticker]
        open_ = close.shift(1).fillna(close.iloc[0] if len(close) else 0.0)
        pair = pd.concat([open_, close], axis=1)
        frames[str(ticker)] = pd.DataFrame(
            {
                BAR_OPEN: open_,
                BAR_HIGH: pair.max(axis=1),
                BAR_LOW: pair.min(axis=1),
                BAR_CLOSE: close,
                BAR_VOLUME: pd.Series(1_000_000.0, index=close.index),
            }
        )[list(BAR_COLUMNS)]
    return frames


def make_fake_bar_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Bars wrapping the same synthetic closes the close-only fixture produces.

    Open is the prior close, and the high/low straddle the bar, so the OHLC
    invariants hold and any test that reads the range gets something a market
    could actually have printed.
    """
    closes = make_fake_close_history(tickers)
    frames: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        close = closes[ticker]
        open_ = close.shift(1).fillna(close.iloc[0])
        frames[ticker] = pd.DataFrame(
            {
                BAR_OPEN: open_,
                BAR_HIGH: pd.concat([open_, close], axis=1).max(axis=1) * 1.01,
                BAR_LOW: pd.concat([open_, close], axis=1).min(axis=1) * 0.99,
                BAR_CLOSE: close,
                BAR_VOLUME: pd.Series(1_000_000.0, index=close.index),
            }
        )[list(BAR_COLUMNS)]
    return frames


def install_backtest_market_data(
    monkeypatch,
    backtest_module,
    *,
    tickers: list[str],
    benchmark_values: list[float],
) -> None:
    monkeypatch.setattr(backtest_module, "load_tickers_from_file", lambda _path: tickers)
    monkeypatch.setattr(
        backtest_module,
        "fetch_bar_history",
        lambda _tickers, _start, _end, **_kwargs: make_fake_bar_history(_tickers),
    )
    monkeypatch.setattr(
        backtest_module,
        "fetch_benchmark_close",
        lambda _ticker, _start, _end, **_kwargs: pd.Series(
            benchmark_values,
            index=pd.date_range("2026-01-01", periods=len(benchmark_values), freq="B"),
        ),
    )


def create_backtest_account(
    conn,
    name: str,
    strategy: str = "trend_v1",
    initial_cash: float = 10000.0,
    benchmark: str = "SPY",
    **kwargs,
) -> None:
    create_account(conn, name, strategy, initial_cash, benchmark, config=AccountConfig(**kwargs) if kwargs else None)


def make_backtest_config(
    account_name: str,
    *,
    start: str = "2026-01-01",
    end: str = "2026-03-01",
    universe_history_dir: str | None = None,
    slippage_bps: float = 5.0,
    fee_per_trade: float = 0.0,
    run_name: str | None = None,
    allow_approximate_leaps: bool = False,
) -> BacktestConfig:
    return BacktestConfig(
        account_name=account_name,
        tickers_file="src/infrastructure/config/trade_universes/default.txt",
        universe_history_dir=universe_history_dir,
        start=start,
        end=end,
        lookback_months=None,
        slippage_bps=slippage_bps,
        fee_per_trade=fee_per_trade,
        run_name=run_name,
        allow_approximate_leaps=allow_approximate_leaps,
    )


def make_backtest_result(
    account_name: str,
    *,
    run_id: int = 1,
    total_return_pct: float = 0.0,
    ending_equity: float = 10_000.0,
    trade_count: int = 1,
    start_date: str = "2026-01-01",
    end_date: str = "2026-02-01",
    tickers: list[str] | None = None,
    benchmark_return_pct: float | None = 0.5,
    alpha_pct: float | None = None,
    max_drawdown_pct: float = -1.0,
    sharpe_ratio: float | None = None,
    sortino_ratio: float | None = None,
    calmar_ratio: float | None = None,
    win_rate_pct: float | None = None,
    profit_factor: float | None = None,
    avg_trade_return_pct: float | None = None,
    warnings: list[str] | None = None,
) -> BacktestResult:
    if alpha_pct is None and benchmark_return_pct is not None:
        alpha_pct = total_return_pct - benchmark_return_pct
    return BacktestResult(
        run_id=run_id,
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        tickers=tickers or ["AAPL"],
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
        max_drawdown_pct=max_drawdown_pct,
        warnings=warnings or [],
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        win_rate_pct=win_rate_pct,
        profit_factor=profit_factor,
        avg_trade_return_pct=avg_trade_return_pct,
    )


def make_backtest_leaderboard_entry(
    account_name: str = "acct1",
    *,
    run_id: int = 1,
    run_name: str | None = None,
    strategy: str = "trend_v1",
    start_date: str = "2026-01-01",
    end_date: str = "2026-03-01",
    created_at: str = "2026-03-17T01:00:00Z",
    trade_count: int = 5,
    ending_equity: float = 10_000.0,
    total_return_pct: float = 0.0,
    max_drawdown_pct: float = -1.0,
    benchmark_return_pct: float | None = None,
    alpha_pct: float | None = None,
) -> BacktestLeaderboardEntry:
    return BacktestLeaderboardEntry(
        run_id=run_id,
        run_name=run_name,
        account_name=account_name,
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        created_at=created_at,
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
    )


def make_backtest_full_report(
    *,
    run_id: int = 1,
    run_name: str | None = "smoke",
    account_name: str = "acct1",
    strategy: str = "trend_v1",
    start_date: str = "2026-01-01",
    end_date: str = "2026-03-01",
    created_at: str = "2026-03-01T00:00:00Z",
    trade_count: int = 3,
    starting_equity: float = 10_000.0,
    ending_equity: float = 10_500.0,
    total_return_pct: float = 5.0,
    max_drawdown_pct: float = -2.0,
    slippage_bps: float = 5.0,
    fee_per_trade: float = 0.0,
    tickers_file: str = "tickers.txt",
    warnings: list[str] | None = None,
    sharpe_ratio: float | None = 1.2,
    sortino_ratio: float | None = 1.5,
    calmar_ratio: float | None = 0.8,
    win_rate_pct: float | None = 60.0,
    profit_factor: float | None = 1.7,
    avg_trade_return_pct: float | None = 2.5,
    benchmark_ticker: str = "SPY",
    benchmark_return_pct: float | None = 1.0,
    alpha_pct: float | None = 4.0,
) -> BacktestFullReport:
    return BacktestFullReport(
        summary=BacktestReportSummary(
            run_id=run_id,
            run_name=run_name,
            account_name=account_name,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            created_at=created_at,
            slippage_bps=slippage_bps,
            fee_per_trade=fee_per_trade,
            tickers_file=tickers_file,
            warnings=[] if warnings is None else warnings,
            trade_count=trade_count,
            starting_equity=starting_equity,
            ending_equity=ending_equity,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            avg_trade_return_pct=avg_trade_return_pct,
        ),
        benchmark_ticker=benchmark_ticker,
        notes=None,
        snapshots=[],
        trades=[],
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
    )


__all__ = [
    "create_backtest_account",
    "bar_frame",
    "bars_from_closes",
    "install_backtest_market_data",
    "make_backtest_config",
    "make_backtest_full_report",
    "make_backtest_leaderboard_entry",
    "make_backtest_result",
    "make_fake_bar_history",
    "make_fake_close_history",
]
