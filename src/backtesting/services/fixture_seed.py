"""Seed one synthetic backtest run for a generated fixture database.

Every row is deterministic, and `tickers_file` carries the `synthetic:` marker so a
generated run is never mistaken for real research.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date

from backtesting.models import BacktestConfig
from backtesting.repositories.runs import insert_run, insert_snapshot, insert_trade

FIXTURE_TICKERS_FILE = "synthetic:FIXTURE"

_SAMPLE_TICKER = "AAPL"
_SAMPLE_QTY = 12.0
_SAMPLE_BUY_PRICE = 150.0
_SAMPLE_SELL_PRICE = 162.0
_FIXTURE_SLIPPAGE_BPS = 2.5


def seed_fixture_backtest(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    account_name: str,
    strategy_key: str,
    benchmark_ticker: str,
    curve: Sequence[tuple[str, float]],
    execution_margin_days: int,
    now_iso: str,
) -> None:
    """Write a run header, two sample executions, and the equity curve.

    ``curve`` is ``(date, equity)`` ascending. The executions are anchored
    ``execution_margin_days`` inside each end so both land on days the curve
    covers.
    """
    run_id = insert_run(
        conn,
        account_id=account_id,
        strategy_name=strategy_key,
        start_date=date.fromisoformat(curve[0][0]),
        end_date=date.fromisoformat(curve[-1][0]),
        cfg=BacktestConfig(
            account_name=account_name,
            tickers_file=FIXTURE_TICKERS_FILE,
            universe_history_dir=None,
            start=curve[0][0],
            end=curve[-1][0],
            lookback_months=None,
            slippage_bps=_FIXTURE_SLIPPAGE_BPS,
            fee_per_trade=0.0,
            run_name="Generated fixture backtest",
            allow_approximate_leaps=False,
        ),
        warnings=[],
        benchmark_ticker=benchmark_ticker,
        benchmark_return_pct=None,
        created_at=now_iso,
        notes="Deterministic synthetic fixture run.",
    )

    for execution_date, side, price in (
        (curve[execution_margin_days - 1][0], "buy", _SAMPLE_BUY_PRICE),
        (curve[-execution_margin_days][0], "sell", _SAMPLE_SELL_PRICE),
    ):
        insert_trade(
            conn,
            run_id=run_id,
            trade_time=execution_date,
            ticker=_SAMPLE_TICKER,
            side=side,
            qty=_SAMPLE_QTY,
            price=price,
            fee=0.0,
            slippage_bps=_FIXTURE_SLIPPAGE_BPS,
            note="Synthetic sample execution",
        )

    opening_equity = curve[0][1]
    for snapshot_date, equity in curve:
        insert_snapshot(
            conn,
            run_id=run_id,
            snapshot_time=snapshot_date,
            cash=equity * 0.35,
            market_value=equity * 0.65,
            equity=equity,
            realized_pnl=max(0.0, equity - opening_equity) * 0.4,
            unrealized_pnl=0.0,
        )
